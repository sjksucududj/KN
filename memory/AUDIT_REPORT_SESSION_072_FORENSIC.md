# FORENSIC AUDIT — Session #072 (Continuation / "Different Approach")

**Tanggal:** (lanjutan setelah restore repo `argentivavsspain/kn`)
**Auditor:** E2 (main agent)
**Permintaan owner:** *"lanjut verifikasi bug dll dulu... lanjutan audit forensik dengan **pendekatan yang berbeda**... semua temuan **ditampung dulu** sampai owner yakin tidak ada celah."*
**Status fixes:** ❌ BELUM ADA FIX DITERAPKAN (sesuai instruksi: kumpulkan temuan dulu).
**Aturan emas:** KODE MENANG atas DOKUMEN — verifikasi = **eksekusi empiris**, bukan pembacaan prosa.

---

## 0. Perbedaan pendekatan vs Session #071

| Session #071 (sudah dilakukan) | Session #072 (INI — lensa baru) |
|---|---|
| 9 lapisan: gates, ruff/ESLint, grep, business-process, handoff, single-request probe, DB dump, FK crawl, state-machine | **Dinamis + keamanan + konkurensi**: AST endpoint-guard, **runtime multi-role probing**, **cross-entity IDOR empiris (read+write)**, **race/idempotency**, rekonsiliasi finansial independen, input-validation fuzzing |
| Fokus: schema drift, silent-fail import | Fokus: **isolasi multi-tenant, otorisasi, integritas transaksional** |

Alat baru dibuat (READ-ONLY, disimpan di `/app/forensic/`): `fa_static.py`, `fa_runtime.py`, `fa_sweep.py`, `fa_idor.py`, `fa_write_idor.py`, `fa_race.py`.

---

## 1. SKORBOARD TEMUAN

| ID | Kategori | Severity | Status bukti | Ringkas |
|---|---|---|---|---|
| **FC-1** | Multi-tenant isolation | **HIGH** | ✅ EMPIRIS (read+write) | Cross-entity IDOR di endpoint by-id: user ter-scope `ent_ksc` **membaca & menulis** dokumen `ent_kanda`. |
| **FC-2** | Multi-tenant isolation (surface) | **HIGH** | ⚠️ STATIS (pola sama, terkonfirmasi di FC-1) | **63 endpoint WRITE + 12 READ** by-id menyentuh koleksi ter-scope **tanpa** `assert_entity_access`; **31** di antaranya dapat dieksekusi role non-lintas-entitas (sales/warehouse). |
| **FB-1** | Auth / data exposure | **HIGH** | ✅ EMPIRIS (unauth) | `GET /documents/preview/{order_id}` **tanpa autentikasi** → render surat-jalan/faktur (nama & alamat customer, baris order) untuk **order apa pun**. |
| **FB-2** | Auth / data exposure | **MEDIUM** | ✅ EMPIRIS (unauth) | `GET /products`, `/uoms`, `/warehouses`, `/pos/best-sellers`, `/pos/substitutes`, `/pos/frequently-bought-together` **tanpa autentikasi**; sebagian menerima `entity_id` bebas (BI lintas-entitas). |
| **FA-*** | Integritas finansial | — | ✅ CLEAN | Trial balance seimbang (global + per-entitas), tiap JE seimbang, header==Σlines, semua account_code ada di CoA, **inventory SSOT** `on_hand == Σ rolls` konsisten. |
| **FD-*** | Race / idempotency | — | ✅ CLEAN | Nomor dokumen atomik (40 konkuren → 40 unik); double-submit approve/confirm = tepat 1 sukses, sisanya 409. |
| **FE-*** | Validasi input finansial | — | ✅ CLEAN | Jurnal tak seimbang ditolak, nominal negatif ditolak, akun header ditolak. |
| **S-10** | Kerahasiaan biaya | — | ✅ CLEAN | Field biaya/HPP/WAC/margin ter-redaksi untuk role sales. |
| **TZ** | Timezone | — | ✅ CLEAN | 0 penggunaan `datetime.now()`/`utcnow()` naif di services/routers. |

> **Catatan koreksi (anti-false-positive):** `GET/PATCH /customers/{id}`, `/customers/{id}/360`, `/credit-status` **AWALNYA terlihat bocor** tetapi TERBUKTI dilindungi `can_access_customer` (guard row-level `assigned_sales_id`). Data seed kebetulan meng-assign customer `ent_kanda` ke user sales uji sehingga guard **lolos secara sah** — **BUKAN bug**. Dikeluarkan dari temuan.

---

## 2. TEMUAN DETAIL

### FC-1 — Cross-entity IDOR (read + write) — **HIGH, EMPIRIS**

**Model keamanan sistem (intent):** user punya `allowed_entity_ids`. Endpoint LIST memakai `resolve_list_scope()` yang **menolak `?entity_id=<entitas lain>` dengan 403**. Helper anti-IDOR `assert_entity_access()` **ADA** dan dipakai di sebagian endpoint (mis. `GET /purchase-orders/{id}` → 403 untuk entitas lain). **Namun tidak konsisten** — banyak endpoint by-id melewatkannya.

**Bukti empiris (user `sales@kainnusantara.id`, `allowed_entity_ids=['ent_ksc']`):**
```
GET  /api/sales-orders?entity_id=ent_kanda           -> 403  (benar: list ter-guard)
GET  /api/sales-orders/so_002   (so_002 = ent_kanda) -> 200  ❌ BOCOR (baca lintas-entitas)
GET  /api/sales-orders/so_002/invoices               -> 200  ❌ BOCOR
PATCH /api/sales-orders/so_002  {"data":{"notes":..}}-> 200  ❌ MENULIS ke order ent_kanda (dikonfirmasi berubah di DB, lalu di-revert)
```
Inkonsistensi terbukti: `resolve_list_scope` memblok (403) tapi endpoint by-id (`get_order`, `update_order`, dst.) hanya `require_permission("order","update")` lalu `find_one({"id": order_id})` **tanpa filter/verifikasi entitas**.

**Dampak:** pelanggaran isolasi multi-tenant — user satu PT dapat membaca/mengubah transaksi PT lain (order, retur, RFQ, tugas WMS, dll.), termasuk mengubah status (cancel, mark-delivered, release-reservation).

### FC-2 — Permukaan lengkap tanpa entity-guard — **HIGH, STATIS**

AST-scan (`fa_idor.py`) atas SEMUA route by-id yang menyentuh koleksi `SCOPED_COLLECTIONS`:
- **63 WRITE** + **12 READ** endpoint **tanpa** guard entitas (`assert_entity_access`/`apply_entity_scope`/`resolve_list_scope`/`can_access_*`).
- Dari WRITE: **31 dapat dieksekusi role non-lintas-entitas** (sales/warehouse memegang permission-nya) → risiko nyata. (Sisanya butuh permission admin/manager yang memang lintas-entitas by-design → risiko lebih rendah.)

**31 endpoint exploitable (ringkas, lihat Appendix A untuk daftar penuh):**
- **sales** (perm `order/price_approval/sales_return/customer`): `PATCH /sales-orders/{id}`, `POST /sales-orders/{id}/{cancel,mark-delivered,release-reservation,submit-for-approval,request-special-price,request-credit-approval,simulate-payment}`, `POST/DELETE .../attachments`, `POST /sales-returns/{id}/submit`, `PATCH/POST /price-approvals/{id}/...`, `PATCH /special-orders/{id}`, `POST /customers/{id}/addresses`.
- **warehouse** (perm `wms/rfq/inventory`): `POST /wms/tasks/{id}/{advance,scan}`, `POST /inbound/tasks/{id}/{complete,scan-receive,qc-decision,escalate}`, `POST /inbound/rolls/{id}/inspect`, `POST /cycle-count/sessions/{id}/items`, `POST /rfqs/{id}/{quote,send,cancel}`, `POST /wms/tasks/outbound-from-order/{id}`, `POST /special-orders/{id}/create-pr`.

### FB-1 — `documents/preview/{order_id}` tanpa auth — **HIGH, EMPIRIS**
```python
# routers/documents.py:102
@router.get("/documents/preview/{order_id}")
async def preview_document(order_id, document_type="surat_jalan", request: Request = None):
    html_content = await render_order_html(order_id, document_type)   # tanpa require_permission
    return HTMLResponse(content=html_content)
```
```
GET /api/documents/preview/so_001?document_type=surat_jalan  (TANPA token) -> 200, HTML 2290B
```
Siapa pun tanpa login dapat menampilkan dokumen order mana pun (nama/alamat customer, baris barang, harga) — lintas-entitas pula.

### FB-2 — Endpoint master/BI tanpa auth — **MEDIUM, EMPIRIS**
```
GET /api/products        (unauth) -> 200 (11 item)
GET /api/uoms            (unauth) -> 200 (6)
GET /api/warehouses      (unauth) -> 200 (3)
GET /api/pos/best-sellers?entity_id=ent_kanda (unauth) -> 200 (BI penjualan; entity_id bebas)
GET /api/pos/substitutes, /pos/frequently-bought-together (unauth) -> 200
```
Handler-handler ini didefinisikan **tanpa** `request`/`require_permission`. Inkonsisten dengan 170 GET lain yang mengembalikan 401 saat unauth. `pos/best-sellers` juga menerima `entity_id` sembarang tanpa validasi (kebocoran BI lintas-entitas).

---

## 3. AREA YANG DIVERIFIKASI BERSIH (bukti empiris)

- **Integritas GL/finansial (FA):** 18 JE semua seimbang; trial balance global & per-entitas seimbang (ksc 99.163.000, kanda 15.700.000); semua `account_code` valid; header==Σlines. 
- **Inventory SSOT (FA):** 17 baris balance roll-tracked == Σ `inventory_rolls.length_remaining` (tak ada drift).
- **Konkurensi (FD):** nomor dokumen 40/40 unik; approve/confirm konkuren = tepat-satu (409 lainnya).
- **Validasi finansial (FE):** jurnal tak seimbang & nominal negatif ditolak.
- **Redaksi biaya (S-10):** sales tak melihat `unit_cost/wac/margin/cogs`.
- **RBAC negatif:** sales/warehouse ditolak 403 di `finance/bi`, `hr/payslips`, `users`, `vendor-bills`, `income-statement`, `tax/summary`.
- **Header `X-Entity-Id: ent_kanda`** oleh user non-allowed: diabaikan (tak bocor di LIST).

---

## 4. BELUM DIJELAJAHI (opsi lanjutan bila owner ingin lebih dalam)

1. **Konfirmasi empiris per-endpoint** untuk 31 endpoint FC-2 (butuh data seed `ent_kanda` lebih kaya di tiap koleksi; kini banyak koleksi hanya berisi `ent_ksc`).
2. **N+1 query / performance** pada endpoint listing besar.
3. **WAC/costing property-based** (jual sebagian roll → retur → restock) — akurasi HPP.
4. **Fuzzing skema mendalam** (boundary qty/price, unicode, payload besar) di seluruh POST.
5. **Frontend authz** — apakah UI menyembunyikan aksi yang backend-nya tembus (defense-in-depth).
6. **Dead endpoints** (BE route tak dipanggil FE) sebagai attack-surface.

---

## Appendix A — Daftar lengkap surface FC-2
(Lihat output `python /app/forensic/fa_idor.py` dan `fa_write_idor.py` untuk 63 WRITE + 12 READ dan pemetaan role.)

## Appendix B — Cara reproduksi
```bash
cd /app
python forensic/fa_static.py       # AST endpoint-guard (55 kandidat, ter-triage)
python forensic/fa_runtime.py      # recon finansial + unauth + isolasi + RBAC (read-only)
python forensic/fa_sweep.py        # unauth sweep semua GET + IDOR sweep
python forensic/fa_idor.py         # surface lengkap /{id} tanpa entity guard + scan money/TZ
python forensic/fa_write_idor.py   # bukti write IDOR (reversible) + cross-ref role
python forensic/fa_race.py         # atomicity nomor dok + double-submit
python forensic/fa_idor_confirm.py # 1a: konfirmasi empiris per-endpoint (user ent_kanda → ent_ksc)
python forensic/fa_costing.py      # 1b: WAC recompute + inventory subledger vs GL
python forensic/fa_nplus1.py       # 1c: N+1 static + latency
python forensic/fa_fuzz.py         # 1e: schema fuzzing
```

---

# BAGIAN II — DEEP-DIVE LANJUTAN (1a–1e) — owner minta "1 semuanya"

> Tetap **TANPA FIX**. Semua ditampung. Data uji di-*clean* via `seed_reset.sh` tiap kali destruktif.

## 1a — KONFIRMASI EMPIRIS PER-ENDPOINT (FC-2) → **14 IDOR TERBUKTI EKSEKUSI**

Metode: dibuat **2 user uji ter-scope HANYA `ent_kanda`** (sales & warehouse), lalu menembak dokumen milik **`ent_ksc`**. Klasifikasi: `403/404`=PROTECTED, `200`=LEAK dieksekusi, `400/409`=LEAK-reached (business-logic jalan di dokumen lintas-entitas).

**LEAK dikonfirmasi (state benar-benar berubah / logika jalan lintas-entitas):**
| Endpoint | Hasil | Catatan |
|---|---|---|
| `PATCH /sales-orders/{id}` | **200** | menulis notes SO ent_ksc |
| `POST /sales-orders/{id}/simulate-payment` | **200** | **MEMBUAT invoice `INV-...` pada order lintas-entitas** (buat dokumen finansial!) |
| `POST /sales-orders/{id}/{cancel,submit-for-approval,release-reservation,mark-delivered}` | 200/409 | transisi status lintas-entitas |
| `PATCH /special-orders/{id}` | 200/409 | |
| `POST /sales-returns/{id}/submit` | 200/409 | |
| `POST /wms/tasks/{id}/advance` | **200** | task WMS ent_ksc di-advance |
| `POST /inbound/tasks/{id}/{complete,qc-decision,escalate}` | 200/409 | |
| `POST /inbound/rolls/{id}/inspect` | **200** | inspeksi roll ent_ksc |
| `POST /wms/tasks/outbound-from-order/{id}` | 200/409 | |

**PROTECTED (bukti inkonsistensi — sebagian SUDAH benar):**
- `POST /sales-orders/{id}/request-special-price` & `/request-credit-approval` → **404 "Data tidak ditemukan untuk entitas ini"** (memanggil `assert_entity_access` ✅)
- `PATCH /price-approvals/{id}`, `/submit` → 403 "hanya pengajuan Anda sendiri" (row-guard `created_by` ✅)
- `special-orders/{id}/create-pr` → 403 (permission block)

**Kesimpulan 1a:** FC-1/FC-2 **TERKONFIRMASI PENUH & 2 arah** (ksc↔kanda). Tingkat keparahan **naik**: `simulate-payment` bahkan **membuat dokumen finansial** pada entitas lain. Ini **BOLA (Broken Object-Level Authorization)** klasik — HIGH.

## 1b — WAC / COSTING
- **WAC benar:** recompute independen == service untuk **33/33** kombinasi (produk×entitas). ✅ CLEAN.
- **Inventory subledger vs GL (OBSERVASI, MEDIUM):** nilai persediaan dari rolls **ent_ksc ≈ Rp 533.712.500**, tetapi **GL akun 1-1300 (Persediaan) hanya Rp 750.000** → selisih ~Rp 533 jt. GL **tidak** mencerminkan nilai persediaan riil ⇒ **Neraca understate persediaan**. Kemungkinan by-design (opening balance harus di-*post* via `POST /gl/inventory-opening-balance` saat go-live) — **direkam untuk keputusan owner**, bukan pasti bug kode.

## 1c — N+1 / PERFORMANCE
- **20 titik query DB di dalam loop** (13 file). Hotspot listing/reporting: `reporting.py:44`, `sales_order_helpers.py:87`, `purchase_orders.py:127`, `ar_receipt_service.py:272`, `customer_service.py:83`, `transfers.py:127/206`, `rfid_service.py`. → **LOW (utang skalabilitas)**, bukan bug fungsional.
- **Latency saat volume seed: semua < 20ms** (tak ada endpoint lambat). Tidak ada isu akut.

## 1d — FRONTEND AUTHZ (defense-in-depth)
- **Tidak ada secret hardcoded** (field `apiKey` di IntegrationsPanel = input user, bukan hardcode). ✅
- Semua panggilan lewat **axios instance terpusat** (Authorization + `X-Entity-Id` default) → **tak ada bypass auth di FE**. ✅
- `navigationConfig` **gating per-role** (122 referensi). ✅
- **Kesimpulan:** isolasi entitas **100% bergantung backend**. FE hanya menampilkan data entitas aktif, jadi user normal tak *melihat* data PT lain — tetapi **API by-id tetap tembus via panggilan langsung** (terbukti di 1a). ⇒ **Fix WAJIB di backend; FE tak bisa memitigasi.**

## 1e — SCHEMA FUZZING (robustness/validasi)
- **0 error 5xx** dari semua payload rusak (negatif, 1e308, unicode/null-byte/RTL, oversized 200KB, mass-assignment, injection-ish) → server **robust terhadap crash**. ✅
- **6 celah VALIDASI (menerima data jelas-invalid, 200):**
  | ID | Endpoint | Masalah | Sev |
  |---|---|---|---|
  | VAL-1 | `POST /products` | **harga negatif (-1) diterima**; SKU dg null-byte/RTL/injection tak disanitasi | MED |
  | VAL-2 | `POST /gl/journal` | **nominal tak berbatas (1e308) diterima** (balanced tapi absurd) → posting jurnal sampah | MED |
  | VAL-3 | `POST /cash-transactions` | **`type` invalid / hilang diterima** (tak ada validasi enum) | MED |
  | VAL-4 | `POST /suppliers` | **`id` dikontrol klien** (`"../../etc/passwd"`) + string tak disanitasi | LOW-MED |

---

# RINGKASAN AKHIR (Bagian I + II)

| Prioritas | Temuan | Bukti |
|---|---|---|
| **P0 HIGH** | **FC-1/FC-2 Cross-entity IDOR (BOLA)** — read+write, 14 endpoint terkonfirmasi eksekusi (termasuk buat invoice lintas-entitas), surface 31 endpoint | EMPIRIS 2 arah |
| **P0 HIGH** | **FB-1** `documents/preview/{id}` tanpa auth | EMPIRIS |
| **P1 MED** | **FB-2** master/BI tanpa auth (`products/uoms/warehouses/pos`) | EMPIRIS |
| **P1 MED** | **1b** GL Persediaan tidak rekonsiliasi dg subledger (Neraca understate) | RECON (perlu konfirmasi intent) |
| **P2 MED** | **VAL-1..3** validasi: harga negatif, nominal tak berbatas, enum type | FUZZ |
| **P3 LOW** | **VAL-4** client-controlled id + sanitasi string; **1c** N+1 skalabilitas | FUZZ/STATIS |
| — CLEAN — | Trial balance, JE balance, inventory SSOT, WAC(33/33), race/idempotency, cost redaction S-10, timezone, RBAC-negatif, FE-authz, 0×5xx | EMPIRIS |

---

# BAGIAN III — DEEP-DIVE RONDE 2 (2a Property-based E2E, 2b AR/AP, 2c Session/Token)

> Tetap **TANPA FIX**. Semua destruktif di-*clean* via `seed_reset.sh`. Semua temuan diverifikasi empiris + akar penyebab dikonfirmasi (reproduksi exception).

## 2a — PROPERTY-BASED END-TO-END (SO → confirm → invoice → retur → restock)

Invarian universal dicek tiap langkah. **Yang TERPENUHI (bagus):**
- **P1** trial balance selalu seimbang (289jt → 294jt, tetap D==C).
- **P2** tiap JE seimbang internal; **P3** inventory SSOT tanpa drift.
- **P5 COGS benar:** COGS ter-posting **1.221.000 == qty×unit_cost** (10×122.100). ✅
- **P6 Sales JE benar** (setelah koreksi akun): Dr Piutang(1-1200) 2.053.500 / Cr Pendapatan(4-1000) 1.850.000 / **Cr PPN Keluaran(2-1200) 203.500**. *(Temuan P6 di draf awal = FALSE POSITIVE: saya cek kode akun PPN yang salah. PPN benar ter-posting.)*

**TEMUAN BARU (HIGH):**

### RET-2 — Retur penjualan GAGAL posting Credit Note + reversal GL (silent) 🔴 HIGH
- Approve sales-return → status "approved", TAPI **tidak ada credit note, tidak ada jurnal reversal**.
- **Akar penyebab (reproduksi):**
  ```
  File ".../services/return_service.py", line 75, in _create_credit_note_and_post_gl
      unit_cost = await gl_service._avg_unit_cost(pid, eid)
  AttributeError: module 'services.gl_service' has no attribute '_avg_unit_cost'
  ```
  `_avg_unit_cost` **tidak ada di mana pun** (kemungkinan di-rename/hapus; helper terdekat: `gl_service._order_item_unit_cost` / `costing_service.wac_for_product`). Exception **ditelan** oleh `try/except` best-effort di `approve_and_adjust_stock` (baris 285-291).
- **Dampak:** SETIAP approve retur **diam-diam gagal** membalik Pendapatan/Piutang/PPN/HPP → buku tetap mencatat penjualan penuh walau barang diretur. Regresi finansial serius & tersembunyi.

### RET-1 — Roll hasil restock retur tanpa `length_remaining` & tanpa cost 🔴 HIGH
- Roll `RTN-...` dibuat dengan `length`/`length_initial` = qty, tetapi **`length_remaining=None`** dan **`unit_cost=None`/`base_unit_cost=None`**.
- **Dampak:** stok retur jadi "hantu" — **tak terhitung** oleh WAC/costing (pakai `length_remaining`×cost) dan berpotensi tak terjual/tak terbiaya (COGS=0 bila dijual lagi). Inkonsistensi skema roll vs roll normal (yang punya `length_remaining`).

### META — Gate `verify_data_integrity.py` BUTA terhadap alur retur 🟠 MED
- Setelah state tercemar (roll retur `length_remaining=None` + retur tanpa reversal GL), gate tetap **PASS 122 | FAIL 0**.
- **Dampak:** RET-1 & RET-2 lolos semua gate → tak akan terdeteksi CI. Perluasan dari temuan S2 (#071): alur **retur→credit-note→GL** & integritas roll-retur **tak diverifikasi**.

## 2b — AR / AP DEEP AUDIT

**AP posting bill: BENAR** — create+post vendor bill: Dr GR/IR(2-1150) 43.100.000 + Dr PPN Masukan(1-1500) 4.741.000 / **Cr Hutang(2-1100) 47.841.000**; trial balance seimbang. Over-billing/over-pay ditolak (400). ✅

### AP-PAY-1 — Pembayaran Vendor Bill TIDAK posting GL (Hutang tak pernah lunas di buku) 🔴 HIGH
- `pay_vendor_bill` **hanya** membuat `cash_transaction(out)` + update status bill → "paid". **TIDAK ada `gl_service` call.**
- Bukti: setelah "pay", GL Hutang(2-1100) **tetap −47.841.000 (Δ=0)**; `cash_transaction` CASH-00013 **tidak punya JE** sama sekali.
- **Dampak:** Hutang Usaha **tak pernah didebit/dilunasi** di GL & Kas tak berkurang di GL saat bayar hutang → **Neraca AP overstated permanen**. Asimetris dg sisi AR (`simulate-payment` yang BENAR posting Dr Kas/Cr Piutang).

### AR-RECON — Observasi (perlu validasi, BUKAN bug terkonfirmasi) 🟡
- GL Piutang(1-1200) ent_ksc **86.913.000** vs subledger Σ(grand_total−paid) **23.171.100**. Cr Piutang di GL = 0 (tak ada receipt ter-posting di seed).
- Kemungkinan **artefak seed/formula** (SO.payments terisi di dokumen tanpa posting receipt GL). Direkam untuk validasi; TIDAK diklaim sebagai bug.

## 2c — SESSION / TOKEN SECURITY

**BERSIH:** entropi token 256-bit ✅; logout meng-invalidate session (401) ✅; token acak ditolak ✅; **session kedaluwarsa ditolak (401)** ✅ *(temuan draf awal = FALSE POSITIVE: test menulis string, sesi asli datetime; dikoreksi)*; `password_hash` tak bocor di `/auth/me` & `/users` ✅; lockout aktif (429 stlh 5 gagal, IP tetap) ✅; cookie **HttpOnly + SameSite=lax** ✅.

**TEMUAN:**
### SES-1 — Cookie sesi tanpa flag `Secure` 🟡 MED
- `set_cookie(..., secure=False, ...)` → cookie bisa terkirim via HTTP (app disajikan via HTTPS ingress → seharusnya `Secure=True` di produksi).

### SES-2 — Bypass lockout brute-force via `X-Forwarded-For` 🟠 MED
- Identifier lockout = `X-Forwarded-For` (dikontrol klien). Bukti: **10 login gagal email sama dg XFF berputar → 0×429** (vs 5 gagal XFF tetap → 429). Penyerang cukup memutar XFF untuk brute-force tanpa terkunci.

---

# SKORBOARD FINAL (Bagian I + II + III)

| Prioritas | ID | Temuan | Bukti |
|---|---|---|---|
| **P0** | FC-1/FC-2 | Cross-entity IDOR/BOLA read+write (14 endpoint terbukti eksekusi 2 arah, surface 31) | EMPIRIS |
| **P0** | FB-1 | `documents/preview/{id}` tanpa auth | EMPIRIS |
| **P0** | RET-2 | Retur: credit-note + reversal GL gagal diam-diam (`_avg_unit_cost` hilang) | EMPIRIS+RCA |
| **P0** | AP-PAY-1 | Bayar vendor bill tak posting GL → Hutang tak pernah lunas di buku | EMPIRIS+RCA |
| **P1** | RET-1 | Roll restock retur tanpa `length_remaining`/cost (stok hantu) | EMPIRIS |
| **P1** | FB-2 | master/BI tanpa auth (`products/uoms/warehouses/pos`) | EMPIRIS |
| **P1** | META-GATE | Gate buta terhadap alur retur (RET-1/RET-2 lolos PASS) | EMPIRIS |
| **P1** | 1b | GL Persediaan tak rekonsiliasi dg subledger (Neraca understate) | RECON |
| **P2** | SES-2 | Bypass lockout via X-Forwarded-For | EMPIRIS |
| **P2** | SES-1 | Cookie tanpa Secure | EMPIRIS |
| **P2** | VAL-1..3 | Validasi: harga negatif, nominal tak berbatas, enum type | FUZZ |
| **P3** | VAL-4, 1c | client-id + sanitasi; N+1 skalabilitas | FUZZ/STATIS |
| **CLEAN** | — | Trial balance, JE balance, inventory SSOT, WAC(33/33), COGS, Sales JE, race/idempotency, cost redaksi S-10, timezone, RBAC-negatif, FE-authz, token/logout/expiry, 0×5xx | EMPIRIS |

**Total temuan actionable:** 4×P0, 4×P1, 4×P2, 2×P3. **Area bersih terverifikasi:** 13+.
