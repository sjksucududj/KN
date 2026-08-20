# KN_21 — PS-21: NOTIFIKASI OPERASIONAL & REPEAT/RESTOCK 1-KLIK

> **Status:** ✅ **SELESAI DIEKSEKUSI** (2026-07-25) · lanjutan sah dari
> `docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md` §5 (“yang belum dikerjakan”).
> **Mandat:** keputusan pemilik sesi 2026-07-25 — “kerjakan **a + b**: quick win PS-21
> lebih dulu, lanjut Fase B (konversi satuan)”.
> **PS tercakup:** **PS-21** (a: alur barang tidak ready → PR 1 klik + notifikasi MD ·
> b: job `po_arrival`, `backorder_ready`, `ar_due_soon` H-3/H-1/H/H+1).
> **Aturan ditegakkan:** R3 (SSOT — tanpa mesin notifikasi/stok/PR kedua) · R5 (desimal) ·
> R6.5/R6.6 (reuse scheduler, digest, eskalasi) · R8 (invarian + POC + dokumentasi).

---

## §1. MASALAH NYATA YANG DITUTUP

| Gejala di lapangan | Sebelum | Sesudah |
|---|---|---|
| Pelanggan minta repeat, barang habis | sales pindah modul, ketik ulang item → sering tidak jadi PR | **1 klik** dari layar order → PR otomatis + MD dinotifikasi |
| Status “pendingan” tidak jelas untuk sales | hanya chip “Backorder” | panel pendingan: diminta / ter-reservasi / pendingan / **stok gudang** + penanda “siap dialokasikan” |
| Barang PO datang tetapi tidak ada yang tahu | harus cek layar penerimaan | notifikasi **seketika** ke MD, gudang, dan sales pemilik order pendingan |
| Pendingan sudah bisa dikirim, sales tidak tahu | tidak ada pemberitahuan | notifikasi “pendingan siap kirim” saat auto-fulfill berhasil |
| Piutang: hanya diingatkan setelah **lewat** jatuh tempo | `ar_overdue` (aging) | + `ar_due_soon` tepat **H-3 · H-1 · H · H+1** tanpa duplikasi |
| PR dobel untuk order & produk yang sama | mungkin terjadi | ditolak 400 + UI menampilkan nomor PR terbuka |

---

## §2. YANG DIBANGUN (backend)

| Berkas | Peran |
|---|---|
| `backend/services/alert_ops_service.py` **(baru)** | 3 generator job PS-21 + `notify_po_arrival()` / `notify_backorder_ready()` (event-driven) + `notify_restock_request()`; semua lewat `create_notification(dedupe_scope="day")` |
| `backend/services/restock_service.py` **(baru)** | `order_restock_state()` (kandidat + pendingan + PR terkait) & `request_repeat_restock()` (buat PR lewat `purchase_requisition_service`, jejak dua arah, audit, notifikasi MD, anti PR dobel) |
| `backend/services/ar_aging_service.py` | `orders_due_soon(offsets)` **baru** — SSOT AR yang sama dengan aging & credit gate (tanpa hitungan sendiri) |
| `backend/services/scheduler_service.py` | registry job **9 → 12**: `po_arrival` (tiap 2 jam), `backorder_ready` (tiap 2 jam), `ar_due_soon` (harian 07:55 WIB) |
| `backend/routers/sales_orders_extra.py` | `GET /api/sales-orders/{id}/restock-state` · `POST /api/sales-orders/{id}/repeat-restock` |
| `backend/schemas.py` | `RepeatRestockItem` / `RepeatRestockIn` (qty desimal koma — PS-15) |
| `backend/routers/inbound_receiving.py` | GR selesai → `notify_po_arrival()` **seketika** (best-effort, tidak menggagalkan GR) |
| `backend/services/backorder_service.py` | auto-fulfill berhasil → `notify_backorder_ready(kind="fulfilled")` |
| `backend/routers/scheduler.py` | **bug fix**: `POST /scheduler/jobs/{id}/run` sebelumnya WAJIB body (422) → body kini opsional |
| `scripts/seed_ar_due_soon_demo.py` **(baru)** | menyiapkan kondisi H-3/H-1/H/H+1 dari order **NYATA** (hanya menggeser tanggal order; nominal/pelanggan tidak diubah) |
| `scripts/verify_data_integrity.py` | **INV-PS21-01…04** (dedupe harian, offset sah, jejak SO↔PR, item PR sah) |
| `backend/test_ps21_poc.py` **(baru)** | POC HTTP tunggal — **43 pemeriksaan**, 10 user story |

### Penerima notifikasi (tanpa sistem izin kedua — R3)

| Jenis | Penerima | Deep-link |
|---|---|---|
| `po_arrival` | `manager` (MD) · `warehouse` · `sales` pemilik order pendingan (`customers.assigned_sales_id`) | `purchasing` / `operations` / `orders` |
| `backorder_ready` | `sales` pemegang akun + `manager` | `orders` |
| `ar_due_soon` | `sales` pemegang akun + `manager` | `ar-aging` |
| `restock_request` | `manager` (MD) | `purchase-requisitions` |

> Catatan Fase H: divisi **MD** sebagai entitas tersendiri (PS-17) belum ada; sampai
> Fase H penerima MD = role `manager`. Ini dicatat agar tidak menjadi asumsi tersembunyi.

---

## §3. YANG DIBANGUN (frontend)

| Berkas | Peran |
|---|---|
| `features/orders/RestockPanel.jsx` **(baru)** | panel “Pendingan & Repeat/Restock” di detail order: status pendingan + stok gudang, modal pilih item (qty desimal koma, saran qty otomatis, estimasi nilai), riwayat permintaan + status PR, penanda PR terbuka, gating role |
| `features/orders/OrderDetailPanel.jsx` | menyisipkan panel PS-21 di detail SO |
| `components/NotificationCenter.jsx` | label jenis baru: Barang PO datang · Pendingan siap · Piutang mendekati jatuh tempo · Permintaan repeat/restock (agar filter jenis di bell tetap ramah-manusia) |

Layar **Pengaturan & Master Data → Penjadwal & Notifikasi** otomatis menampilkan 3 job baru
(jadwal, terakhir jalan, tombol Jalankan, riwayat per job) karena UI membaca `/api/scheduler/jobs`
— tidak ada daftar job yang di-hardcode di FE.

---

## §4. BUKTI

| Bukti | Hasil |
|---|---|
| POC `backend/test_ps21_poc.py` | **43 PASS · 0 FAIL** (10 user story) |
| Invarian | **INV-PS21-01…04 PASS** · total `verify_data_integrity.py` **154 PASS / 0 FAIL / 0 WARN** |
| Fase A tidak regresi | `backend/test_fase_a_poc.py` **53 PASS · 0 FAIL** |
| Gate | `scripts/gate.sh` — 12/12 HIJAU |
| Bukti data nyata | `python scripts/seed_ar_due_soon_demo.py --run` → 4 order pada 4 offset → 8 notifikasi |

---

## §5. CARA UJI CEPAT

```bash
cd /app
python scripts/seed_ar_due_soon_demo.py --run   # kondisi H-3/H-1/H/H+1 dari order nyata
python backend/test_ps21_poc.py                  # harus 43 / 0
python scripts/verify_data_integrity.py          # harus 154 PASS / 0 FAIL
bash scripts/gate.sh                             # 12/12 hijau
```
UI: preview → quick-login **Sales** → *Penjualan → Pesanan (SO)* → pilih order →
panel **“Pendingan & Repeat/Restock”** → *Minta Repeat/Restock*.
Login **Manager** → bell → filter jenis **“Permintaan repeat/restock”**.
Login **Admin** → *Pengaturan & Master Data → Penjadwal & Notifikasi* → 12 job (3 baru) →
tombol **Jalankan** + ubah jadwal.

---

## §6. BATAS TEGAS (tidak dikerjakan di PS-21)

* Divisi & penugasan berbasis divisi (PS-17/PS-18) → **Fase H**.
* Kanal WhatsApp nyata (Fonnte/Meta Cloud) tetap `simulated` sesuai keputusan pemilik R6.5.
* Konversi satuan (`doc_*`/`base_*`, `uom_conversion_rules`) → **Fase B** (`docs/KN_22`).
