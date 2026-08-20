# KN_36 — FASE G-6: TRANSAKSI ANTAR ENTITAS (bukan lagi “transfer”)

> Spesifikasi asal: `plan.md` §G-6 (permintaan pemilik #6) · urutan §G-11 setelah G-7.
> Dependensi **sudah lengkap**: G-1 (koreksi ber-alasan) · G-4 (relasi dokumen) ·
> G-7 (kontrabon — pola “satu dokumen menutup banyak transaksi” dipakai ulang untuk
> **settlement/netting**) · M-3 (posting jurnal antar-PT at-cost yang sudah ada).
> **Status: ✅ DITUTUP (2026-07-30, repo `ghananamakaa/kn`).** Tiga keputusan pemilik
> (bagian 6) dipatuhi penuh. Hasil & bukti penutupan: **bagian 8**.

---

## 1. Masalah nyata

Pemilik menegaskan: **antar entitas itu jual-beli, bukan pindah gudang.** PT KSC menjual
kain ke CV Kanda dengan harga khusus dan **mengambil margin**; keduanya PT terpisah dengan
buku, pajak, dan pelanggan sendiri.

| Kenyataan lapangan | Kondisi sistem hari ini |
|---|---|
| Antar PT = jual-beli berharga khusus, ada **margin** | hanya ada perpindahan **at-cost** (`gl_service.post_intercompany_transfer`) — margin tidak pernah ada |
| Tiap PT butuh **dokumen sendiri** (PO internal di pembeli, SO + Surat Jalan + Invoice di penjual) | hanya **satu** dokumen `warehouse_transfers` dipakai bersama dua PT — tidak ada surat yang bisa ditandatangani/dikirim masing-masing pihak |
| Perlu tahu **“CV Kanda utang berapa ke KSC”** setiap saat | tidak ada saldo antar-PT; harus menjumlahkan jurnal `1-1250`/`2-1250` sendiri |
| Utang antar-PT dilunasi **berkala sekaligus** (netting/settlement) | tidak ada dokumen pelunasan antar-PT |
| Laba antar-PT **wajib dieliminasi** selama barang belum terjual ke pihak luar | eliminasi baru pada level **pasangan akun** (`sync_ic_eliminations_from_pairs`) — **unrealized profit persediaan tidak dihitung** |
| Istilah di layar masih “Transfer Antar-Entitas” | menyesatkan: terbaca seperti mutasi gudang, padahal ini transaksi dagang |

Baris terakhir bukan soal kata: selama antar-PT diperlakukan sebagai “transfer”, **tidak ada
harga, tidak ada margin, tidak ada piutang** — dan laporan laba per PT ikut salah.

---

## 2. Temuan awal (dibaca dari kode, sebelum menulis apa pun)

| # | Temuan | Konsekuensi desain |
|---|---|---|
| 1 | Perpindahan antar-PT hidup sebagai `warehouse_transfers` + `routers/transfers.py` `POST /transfers/inter-company`; eksekusinya `execute_ownership_transfer()` | G-6 **tidak membuang** jalur itu: ia menjadi **lapisan gudang** (fisik barang). Yang ditambahkan adalah **lapisan dagang** di atasnya |
| 2 | `gl_service.post_intercompany_transfer` sudah memposting **dua** jurnal seimbang (`Dr 1-1250 IC-AR / Cr 1-1300` di penjual · `Dr 1-1300 / Cr 2-1250 IC-AP` di pembeli), **idempotent** per `transfer_id` + suffix `:src`/`:dst` | mesin dua-buku sudah terbukti. G-6 memperluasnya agar mengenal **harga jual internal** (margin → `4-xxxx` penjual, HPP → persediaan pembeli) |
| 3 | Nilainya **at-cost by design** (“no IC profit sampai barang dijual ke external”) | keputusan lama itu HARUS dibuka: pemilik minta margin. Karena itu **eliminasi unrealized profit** menjadi bagian wajib fase ini, bukan opsional |
| 4 | `supplier_contracts` sudah punya `partner_kind` (`supplier` / `makloon`) lewat `contract_service` | harga khusus internal = `partner_kind="entity"` + `ic_pricing_mode` — **bukan** koleksi harga baru |
| 5 | `consolidation_service` punya `_pair_totals()` + `sync_ic_eliminations_from_pairs()` (eliminasi otomatis dari pasangan akun IC) | eliminasi saldo sudah ada; yang belum: **laba tertahan di persediaan** milik pembeli yang belum terjual keluar |
| 6 | Tidak ada koleksi saldo antar-PT (`intercompany_accounts` **belum ada**) | butuh buku besar ringkas per **pasangan entitas** + dokumen **settlement** (pola kontrabon G-7: satu dokumen menutup banyak transaksi) |
| 7 | `entity_scope.py` sudah menegakkan isolasi lintas-PT untuk semua koleksi ber-`entity_id` | transaksi antar-PT adalah **satu-satunya** dokumen yang sah menyentuh dua PT → butuh pola “dokumen kembar” (satu di tiap PT, saling `refs`), BUKAN pelemahan scoping |
| 8 | G-9 punya playbook `salah_entitas` yang merujuk kemampuan pindah-buku antar-PT | penutupan G-6 memberi playbook itu jalur dokumen resmi (bukan koreksi senyap) |

---

## 3. Yang akan dibangun

### 3.1 Backend
| Berkas | Isi |
|---|---|
| `services/interco_service.py` | Mesin transaksi antar-PT: `quote()` (harga internal dari kontrak) · `create()` (dokumen kembar) · `confirm/ship/receive/invoice` · `settle()` |
| `services/interco_settlement.py` | **Netting**: satu dokumen pelunasan menutup banyak transaksi antar-PT (pola kontrabon) |
| `routers/interco.py` | `/api/interco/*` — daftar, detail, quote, siklus, saldo pasangan PT, settlement |
| `schemas_interco.py` | Model Pydantic (`MoneyDecimal`/`QtyDecimal` PS-15) |
| `config_catalog_interco.py` | Grup **`antar_entitas`** di Pusat Pengaturan (mode harga bawaan · ambang persetujuan · wajib settlement per N hari · akun margin) |
| `services/gl_service.py` | perluas `post_intercompany_transfer` → **harga jual** (bukan hanya cost): margin ke pendapatan penjual, HPP ke persediaan pembeli |
| `services/consolidation_service.py` | **eliminasi unrealized profit** persediaan antar-PT yang belum terjual keluar |
| `scripts/verify_data_integrity.py` | lapisan `interco` — **INV-IC-01..04** |

### 3.2 Koleksi
* `interco_transactions` (`ict_`, nomor `<ENT>/IC-#####`) — **dokumen kembar**: satu baris per
  PT (`role: seller|buyer`) yang saling menunjuk lewat `refs` (G-4) + `pair_id` bersama.
* `interco_accounts` (`ica_`) — saldo IC-AR/IC-AP per **pasangan entitas** + deposit.
* `interco_settlements` (`ics_`, nomor `<ENT>/ICS-#####`) — pelunasan/netting berkala.

### 3.3 Siklus
`draft → confirmed → shipped → received → invoiced → settled` (+ `disputed` / `cancelled`),
dengan barang fisiknya tetap berjalan lewat jalur gudang yang sudah ada (temuan #1).

### 3.4 Invarian baru
* **INV-IC-01** — setiap transaksi antar-PT punya **pasangan jurnal seimbang di DUA buku**
  (tidak ada dokumen yang hanya membebani satu PT).
* **INV-IC-02** — `IC-AR` di PT penjual **sama besar** dengan `IC-AP` di PT pembeli untuk
  setiap pasangan entitas (setelah settlement diperhitungkan).
* **INV-IC-03** — margin antar-PT **ter-eliminasi** di konsolidasi selama barangnya belum
  terjual ke pihak luar (unrealized profit).
* **INV-IC-04** — saldo `interco_accounts` == Σ transaksi − Σ settlement (tidak boleh drift).

---

## 4. User stories (dipakai juga sebagai skenario uji)
| # | Sebagai | Saya ingin | Bukti lulus |
|---|---|---|---|
| US1 | Pemilik | antar-PT diperlakukan **jual-beli**, bukan pindah gudang | istilah layar & dokumen berubah; harga internal tampil |
| US2 | Pembeli (PT B) | menerbitkan **PO internal** ke PT penjual | dokumen kembar lahir, saling `refs` |
| US3 | Penjual (PT A) | menerbitkan **SO + Surat Jalan + Invoice internal** | 3 dokumen nyata, bisa dicetak & ditandatangani |
| US4 | Keuangan | **harga khusus internal** dari kontrak (`at_cost` / `cost_plus_pct` / `fixed_price`) | ubah kontrak → harga transaksi berubah |
| US5 | Keuangan | melihat **saldo antar-PT** kapan saja | layar saldo per pasangan PT = Σ transaksi − Σ settlement |
| US6 | Keuangan | melunasi banyak transaksi antar-PT **sekali** (netting) | 1 `interco_settlements` menutup ≥2 transaksi; kedua buku bergerak |
| US7 | Akuntan | margin antar-PT **tidak** menggelembungkan laba grup | konsolidasi mengeliminasi unrealized profit; terbukti bukti-merah |
| US8 | Gudang | barang tetap berjalan lewat tugas gudang biasa | roll berpindah PT lewat jalur yang sudah ada, tanpa dobel mutasi |
| US9 | Manajer | persetujuan sesuai **ambang dari Pusat Pengaturan** + pemisahan tugas | > ambang butuh admin; pembuat ≠ penyetuju |
| US10 | Semua | relasi dokumen dua arah + jejak waktu | `refs` PO internal ↔ SO ↔ Surat Jalan ↔ Invoice ↔ settlement |
| US11 | Admin | isolasi lintas-PT tetap utuh & invarian dijaga gate | PT ketiga → 403; INV-IC-01..04 bukti-merah |

---

## 5. Risiko & mitigasi
| Risiko | Mitigasi |
|---|---|
| Mengubah `post_intercompany_transfer` bisa merusak jurnal M-3 yang sudah berjalan | jalur at-cost lama **dipertahankan** untuk data lama; harga jual hanya untuk dokumen G-6 (dibedakan `source_type`) |
| Dokumen kembar bisa menjadi celah lintas-PT | pola “satu dokumen per PT” + `pair_id`; `entity_scope` TIDAK dilonggarkan |
| Eliminasi unrealized profit butuh jejak stok asal | dipakai `inventory_rolls` (Roll-as-SSOT) yang sudah menyimpan asal & cost |

---

## 6. Keputusan pemilik — **SUDAH DIPUTUS 2026-07-30**

| # | Pertanyaan | Keputusan pemilik | Konsekuensi desain (WAJIB diikuti saat eksekusi) |
|---|---|---|---|
| 1 | Mode harga antar-PT | **`fixed_price`** — harga tetap per barang, diatur di **kontrak internal** | Mode bawaan config `antar_entitas.pricing_mode = fixed_price`. Harga hidup di `supplier_contracts` ber-`partner_kind="entity"` (per barang). **Transaksi DITOLAK dengan kalimat menuntun bila barangnya belum punya harga internal di kontrak aktif** — sistem TIDAK BOLEH menebak harga (mis. memakai WAC diam-diam). `at_cost` & `cost_plus_pct` tetap tersedia sebagai pilihan per kontrak; dokumen lama yang at-cost (M-3) tetap sah dan tidak diubah |
| 2 | PPN internal | **Bisa dua-duanya, tergantung entitas** | Kunci config **ber-scope PT** `antar_entitas.ppn_mode` (Pusat Pengaturan G-0 sudah mendukung scope entity): `ikut_pkp` *(bawaan — mengikuti status PKP entitas penjual)* · `tanpa_ppn` · `dengan_ppn`. Bila berujung ber-PPN: penjual menerbitkan **faktur pajak keluaran**, pembeli mencatat **PPN masukan** dengan DPP & tarif yang sama. Invarian tambahan **INV-IC-05**: PPN keluaran penjual == PPN masukan pembeli untuk transaksi yang sama; bila `tanpa_ppn`, kedua sisi WAJIB nol (tidak boleh miring sebelah) |
| 3 | Ritme settlement | **Sewaktu-waktu** saat Keuangan menekan tombol (tanpa jadwal) | **TIDAK ADA job penjadwal netting.** Layar *Saldo Antar-PT* punya tombol **“Buat Settlement”** yang merakit transaksi terbuka satu pasangan PT (pola kontrabon G-7: satu dokumen menutup banyak transaksi). Sebagai ganti jadwal, config opsional `antar_entitas.settlement_reminder_days` menerbitkan **pengingat** bila saldo menganggur lebih lama dari N hari — mengingatkan, bukan memaksa |

Dua penegasan yang mengikat dari keputusan #1 & #2:
* karena harganya **tetap dari kontrak**, margin antar-PT menjadi angka yang bisa diaudit
  (harga kontrak − HPP penjual) → **eliminasi unrealized profit di konsolidasi WAJIB** ada
  di fase ini, bukan ditunda (INV-IC-03);
* karena PPN **berbeda per PT**, seluruh angka pajak transaksi antar-PT harus diambil dari
  config ber-scope PT — **tidak boleh ada tarif/keputusan PPN yang ditulis di kode**.

## 7. Urutan eksekusi yang disarankan
`G-6.0` fondasi config + kontrak `partner_kind="entity"` → `G-6.1` dokumen kembar + siklus →
`G-6.2` jurnal berharga + eliminasi unrealized profit → `G-6.3` saldo & settlement →
`G-6.4` layar (Transaksi Antar-Entitas · Saldo Antar-PT · Settlement) → `G-6.5` POC +
invarian + gate.

## 8. Hasil penutupan — ✅ **2026-07-30** (repo `ghananamakaa/kn`)

### 8.1 Bukti (bisa diulang siapa pun)
```bash
cd /app/backend && python -m pytest tests/test_g6_poc.py -q   # 21 PASS / 0 FAIL
cd /app && python scripts/verify_data_integrity.py            # 229 PASS / 0 FAIL / 0 WARN
cd /app && python scripts/verify_data_integrity.py --only interco   # INV-IC-01..06 (6 PASS)
cd /app && bash scripts/gate.sh --full                        # SEMUA GATE HIJAU (POC G-6 terdaftar)
```
`testing_agent_v3` **iter_191** (BE 13/14 · FE 100%) + **iter_192** (BE 14/15 · alur sisa),
ditambah verifikasi layar oleh main agent untuk 3 alur yang tak terjangkau agen.

### 8.2 Titik henti sesi sebelumnya — apa yang benar & apa yang belum
| Klaim titik henti | Verifikasi di lingkungan baru |
|---|---|
| POC G-6 15/15 hijau | ✅ benar (`pytest tests/test_g6_poc.py`) |
| backend interco + eliminasi margin ada | ✅ benar (`interco_service.py` 910 baris · `sync_g6_ic_eliminations`) |
| UI Interco (view · create · settlement · detail · wizard kontrak) ada | ✅ benar, dan hidup di layar |
| “blok jurnal” di Detail Panel | ❌ **tidak pernah tampil** — layar memanggil `/api/gl/entries` (404) & galatnya ditelan `try/catch` |
| eliminasi bisa dipakai user | ❌ **tanpa pemicu di layar** (`POST /api/consolidation/sync-g6` hanya bisa lewat curl) |
| invarian INV-IC-01..05 dijaga gate | ❌ **belum ada** di `scripts/verify_data_integrity.py`; POC G-6 juga belum di `gate.sh` |
| data demo G-6 | ❌ layar **kosong** setelah `seed_realistic.py` |
| US8 “barang lewat gudang tanpa dobel” | ❌ **berisiko dobel**: transfer antar-PT tetap memposting jurnal at-cost M-3 |

### 8.3 Yang dibangun/diperbaiki di sesi penutupan
**Jembatan gudang (US8) — akhirnya nyata**
* `POST /api/interco/transactions/{id}/warehouse-task` menerbitkan `warehouse_transfers`
  ber-`interco_pair_id` (reservasi roll penjual, satu tugas per transaksi).
* Saat gudang menyetujuinya (`POST /api/transfers/{id}/approve`): jurnal **at-cost M-3
  DILEWATI** dengan alasan tercatat (`je_intercompany.posted=false`), roll di pembeli
  **dinilai ulang** ke harga beli internal, dan status pair maju otomatis ke `received`.
* `inventory_lots` ikut **berpindah rumah** ke PT tujuan (genealogi menunjuk lot asal) —
  menutup pelanggaran INV-LOT-05 “lot tidak lintas pemilik” yang sebelumnya mustahil
  terlihat karena data demo tidak pernah memindahkan kepemilikan.

**Jurnal MENGIKUTI BARANG (akun baru `1-1310`)**
* Saat **dikonfirmasi**: penjual `Dr 1-1250 / Cr 4-1000 + 2-1200`; pembeli
  `Dr 1-1310 Persediaan Dalam Perjalanan + 1-1500 / Cr 2-1250`.
* Saat **barang berpindah**: penjual `Dr 5-1000 / Cr 1-1300` (biaya NYATA roll yang keluar,
  bukan WAC×qty); pembeli `Dr 1-1300 / Cr 1-1310`.
* Hasil terukur: WARN `INV-GL-DRIFT` (persediaan subledger vs GL 1-1300) **hilang** —
  integritas dari 228 PASS/1 WARN menjadi **229 PASS / 0 WARN**.
* Konsekuensi UX yang disengaja: tombol “Tandai Diterima” **menolak** bila barangnya belum
  berpindah, dengan kalimat menuntun ke *Buat Tugas Gudang*.

**Eliminasi unrealized profit jadi OTOMATIS & selalu mutakhir (US7/INV-IC-03)**
* Disinkronkan sendiri saat transaksi dikonfirmasi · barang diterima · dilunasi · dibatalkan.
* `sync_g6_ic_eliminations` kini **create + update + remove** (bukan “sudah ada → lewati”),
  melaporkan `created/updated/removed/skipped_existing/pairs_seen`.
* Margin bersarang di akun yang benar: `1-1310` selama barang di jalan, `1-1300` setelah tiba.

**Pembatalan ber-alasan yang MEMBALIK jurnal (pola G-1)**
* `cancel` menolak tanpa alasan (≥5 huruf) untuk dokumen yang sudah dikonfirmasi,
  menerbitkan jurnal pembalik `{pair}:{sisi}:reversal` di kedua buku, membatalkan tugas
  gudang yang masih menunggu (roll dilepas), dan menghapus entri eliminasinya.

**Layar (frontend) — fitur backend tidak boleh tak terjangkau**
* `GET /api/interco/transactions/{id}/journal` (baru) → Detail Panel menampilkan
  **Jurnal Buku Penjual/Pembeli · Jurnal HPP · Jurnal Penerimaan · Jurnal Pembalik ·
  Eliminasi Grup (badge AUTO G-6) · Tugas Gudang** + kalimat “jurnal at-cost dilewati”.
* Daftar transaksi: kolom **Barang Fisik**, aksi **Buat Tugas Gudang**, keadaan
  **Menunggu gudang menyetujui** (disabled), dan **Batalkan** lewat modal beralasan.
* Konsolidasi Grup: tombol **Sinkron Antar-PT (G-6)** & **Sinkron Pasangan Jurnal (M-3)**,
  hitungan “N otomatis dari transaksi antar-PT”, badge **AUTO G-6**, dan entri auto
  **tidak bisa dihapus manual** (“dikelola sistem”).

**Gate & data demo**
* `scripts/verify_data_integrity.py` lapisan `interco`: **INV-IC-01..06** (IC-06 = jembatan
  gudang: tanpa jurnal dobel + roll dinilai ulang + transit nol setelah diterima).
* POC G-6 terdaftar di `gate.sh --full`; POC kini **bukti-merah** (menyuntik pelanggaran →
  invarian WAJIB memerah → pulihkan) dan **nol residu** (snapshot/restore stok).
* `seed_interco()` di `seed_realistic.py` lewat **jalur produksi (ASGI in-process)**:
  4 transaksi (1 diterima lewat tugas gudang · 1 lunas netting · 1 dikonfirmasi menunggu
  kirim · 1 draf) + 3 kontrak harga internal + 3 eliminasi otomatis.
* `interco_accounts` mendapat `entity_id` (F0-C), dan `interco_transaction` /
  `interco_settlement` terdaftar di `doc_refs_service` (dokumen kembar & settlement kini
  ber-relasi dua arah, bisa ditelusuri dari Pusat Dokumen).

### 8.4 Status 11 user story
| US | Bukti |
|---|---|
| US1 jual-beli, bukan pindah gudang | harga internal + margin tampil di layar & jurnal; `pricing_modes` di `/interco/meta` |
| US2 PO internal pembeli | dokumen kembar `pair_id` + `counterpart_id/number` (POC US2/US3) |
| US3 SO+SJ+Invoice penjual | dokumen sisi penjual + jurnal & faktur internal (status `invoiced`) |
| US4 harga dari kontrak | ubah `tariff_rate` → transaksi baru ikut harga baru (POC US4) |
| US5 saldo antar-PT | tab *Saldo Antar-PT* + `interco_accounts` (INV-IC-04) |
| US6 netting banyak transaksi | 1 `interco_settlements` menutup ≥2 transaksi, dua buku bergerak (POC US6) |
| US7 margin tak menggelembungkan laba grup | eliminasi OTOMATIS + `sync-g6` di layar (INV-IC-03) |
| US8 barang lewat gudang, tanpa dobel | tugas gudang tertaut · at-cost dilewati · roll dinilai ulang (INV-IC-06) |
| US9 ambang persetujuan | >Rp100jt butuh admin (POC US9, manager ditolak 400) |
| US10 relasi dua arah + jejak waktu | `refs[]` dua arah + timeline (termasuk alasan pembatalan) |
| US11 isolasi PT + invarian | gudang tak boleh `create` (403) · INV-IC-01..06 bukti-merah · `entity_id` di 3 koleksi |

### 8.5 Catatan untuk sesi berikutnya
* Faktur internal masih **stempel status** (`invoiced`): kalau pemilik ingin **faktur pajak
  keluaran/masukan nyata** untuk transaksi antar-PT ber-PPN, itu pekerjaan lanjutan
  (menyambung ke `tax_invoices`).
* Retur antar-PT belum ada: dokumen yang sudah `received` hanya bisa dikoreksi lewat
  pembatalan sebelum barang berpindah (sesudahnya sengaja DITOLAK dengan pesan “buat retur”).
* `settlement_reminder_days` sudah jadi config & tampil sebagai penanda “menganggur” di tab
  Saldo Antar-PT, tetapi **belum** menerbitkan notifikasi terjadwal.


---

## 9. FASE G-6b — 4 LANJUTAN (✅ **DITUTUP 2026-08-06**)

Permintaan pemilik sesudah G-6 ditutup: kerjakan 4 lanjutan yang tercatat sebagai
*"kandidat berikutnya"*.

| # | Lanjutan | Hasil |
|---|---|---|
| A | **Faktur Pajak Internal ber-PPN** | `services/interco_tax_service.py` — pasangan dokumen NYATA: keluaran (`tax_invoices`) di buku penjual + masukan (`tax_invoices_in`) di buku pembeli, DPP & PPN sama besar, `source_type="interco"` sehingga **rekap `vat_summary` tiap PT ikut jujur** (sebelumnya seluruh PPN antar-PT tidak pernah muncul di posisi kurang/lebih bayar). Terbit hanya setelah **faktur internal** ada; transaksi tanpa PPN ditolak dengan kalimat menuntun. Retur → faktur ditandai **perlu pengganti** (dokumen terbit tidak diedit). 4 endpoint + modal layar. |
| B | **Retur Antar-PT** | `services/interco_return_service.py` + koleksi `interco_returns` (`icr_`, `<ENT>/ICR-#####`) — **dokumen kembar** (nota retur ↔ nota kredit), **dual-control** (pembuat ≠ penyetuju), jurnal dipisah seperti G-6: sisi DOKUMEN saat disetujui (`4-1000`/`2-1200` vs `1-1250`; `2-1250` vs `1-1310`/`1-1500`), sisi BARANG saat **tugas gudang ARAH BALIK** selesai (`1-1310`→`1-1300` di pembeli; `1-1300`←`5-1000` di penjual pada **harga perolehan ASLI**). Roll dinilai ulang kembali & tanda pair dilepas. Saldo antar-PT berkurang lewat `returned_amount` — nilai dokumen TIDAK pernah diedit. |
| C | **Pengingat Settlement** | `services/interco_reminder.py` + job `interco_settlement_reminder` (harian 07:40 WIB). **Mengingatkan, bukan memaksa** — netting tetap manual (keputusan pemilik #3). Tombol **Ingatkan** per pasangan PT + `GET /api/interco/reminders`. Umur saldo kini dari **aktivitas nyata** (KN-G6-IDLE-FAKE). |
| D | **Rapor Margin Grup** | `services/interco_margin.py` + tab **Rapor Margin**: margin dipecah **realized vs unrealized** dari sisa panjang roll bertanda (data nyata). Mesin eliminasi konsolidasi ikut diperbaiki agar **hanya margin belum terealisasi** yang dihapus (KN-G6-ELIM-FULL-MARGIN). |

### 9.1 Invarian baru
* **INV-IC-07** — faktur pajak internal selalu berpasangan (DPP & PPN sama besar,
  buku benar, hanya untuk transaksi ber-PPN); angka boleh tertinggal HANYA bila
  ditandai *perlu pengganti*.
* **INV-IC-08** — retur berjurnal berpasangan seimbang di dua buku, jumlah retur tak
  pernah melebihi transaksi asal, `returned_amount` == Σ retur berlaku, dan retur
  `completed` wajib punya tugas gudang selesai + jurnal barang.
* **INV-IC-03 diperkuat** — memakai identitas `Dr Pendapatan S · Cr HPP (S−M·u) ·
  Cr Persediaan (M·u)` dan membandingkan `g6_unsold_ratio` tersimpan dengan hitung
  ulang lewat helper yang sama.
* **INV-IC-04 diperkuat** — sisa = nilai − terlunasi − **diretur**.

### 9.2 Bukti (bisa diulang siapa pun)
```bash
cd /app/backend && python -m pytest tests/test_g6b_poc.py -q   # 15 PASS / 0 FAIL
cd /app/backend && python -m pytest tests/test_g6_poc.py -q    # 21 PASS / 0 FAIL
cd /app && python scripts/verify_data_integrity.py             # 231 PASS / 0 FAIL / 0 WARN
cd /app && bash scripts/gate.sh --full                         # SEMUA GATE HIJAU (160s)
```
`testing_agent_v3` iter_193: **backend 53/53 (100%)**. Temuan FE "routing
/finance/interco" adalah **false positive** — aplikasi ini tidak punya routing
berbasis URL sama sekali (117+ layar lewat `activeView`); layar diverifikasi
langsung lewat Playwright oleh main agent (5 tab + siklus modal faktur pajak
terbit→batal). **4 bug NYATA** ditutup: `memory/BUG_REGISTRY.md` §2026-08-06.

### 9.3 Layar
**Pembelian → Hutang Supplier (AP) → Antar Entitas (Jual-Beli)** — 5 tab:
*Daftar Transaksi* (kolom **Pajak** + tombol Faktur Pajak/Retur) · *Saldo Antar-PT*
(kolom **Diretur** + tombol **Ingatkan**) · *Settlement* · **Retur Antar-PT** ·
**Rapor Margin**. Panel detail transaksi menambah blok **Faktur Pajak Internal** &
**Retur Antar-PT** (beserta 4 blok jurnalnya).

### 9.4 Yang BELUM (kandidat berikutnya, jujur)
* **G-5 Unlock Periode Berotoritas** — belum ada kode sama sekali (fase terakhir §G-11).
* **Utang teknis §G-12 / F-2** — contract picker di PO manual + jejak sourcing di `PODetailPanel`.
* Cetak PDF nota retur & faktur pajak internal (saat ini tampil di layar, belum ada template cetak).
* NSFP resmi DJP untuk faktur internal masih diisi manual (belum ada alokasi otomatis).
