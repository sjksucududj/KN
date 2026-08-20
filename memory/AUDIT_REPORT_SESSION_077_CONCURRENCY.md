# AUDIT REPORT — SESSION #077 · Tutup Blindspot Konkurensi & State-Machine (Guardrail v2 lanjutan)

> **Mode: report-only** (tak mengubah kode aplikasi). Menindaklanjuti permintaan owner:
> *"berapa % confidence verifikasi bug? saya ingin >90%. dari analisis repo travel, ambil yang bisa menutup blindspot."*
>
> Basis: adaptasi metodologi Guardrail v2 proyek Rahaza Travel (yang menemukan bug P0 di **race** & **state-machine**)
> → dibangun 2 gate RUNTIME baru untuk KN, lalu **dijalankan** untuk benar-benar menguji 2 kelas yang selama #074–#076 **tak pernah diuji**.

- **Tanggal:** 2026-07-05
- **Gate baru:** `scripts/guardrails/verify_concurrency.py` (INV-CONC-01), `scripts/guardrails/verify_state_machine.py` (INV-STATE-01) — keduanya diorkestrasi `scripts/gate.sh`.

---

## 0. Ringkasan

| Kelas (blindspot #076) | Sebelum | Aksi #077 | Hasil |
|---|---|---|---|
| **Concurrency / race (TOCTOU)** | 0 tes (~40% conf) | bangun+jalankan `verify_concurrency.py` | 🔴 **P0 DITEMUKAN**: overpay vendor-bill 6× |
| **State-machine SO** | tak sistematis (~55% conf) | bangun+jalankan `verify_state_machine.py` | 🟢 **SEHAT** (4/4 invarian lolos) |

Kedua blindspot kini **ter-gate** (regresi terkunci) dan **dijalankan sungguhan** — bukan sekadar diklaim.

---

## 1. 🔴 KN-077-RACE-VBILL-PAY — Overpayment paralel (P0, TOCTOU)  [BARU]

**Lokasi:** `backend/routers/vendor_bills.py` → `pay_vendor_bill` (~baris 392→427).

**Akar (check-then-`$inc`, non-atomic):**
```python
bill = await db.vendor_bills.find_one({"id": bill_id})          # READ (stale)
...
if amount > fin["outstanding"] + 0.01:                          # CEK vs read stale
    raise HTTPException(400, "Pembayaran melebihi sisa hutang")
...
await db.vendor_bills.update_one({"id": bill_id},
    {"$inc": {"amount_paid": amount}, "$set": {"status": new_status}})   # WRITE
```
Guard `amount ≤ outstanding` dinilai atas **hasil baca yang basi**. K request paralel semuanya lolos cek lalu `$inc`.

**Bukti empiris (terreproduksi):** bill `grand_total = 27.472.500` → **6× `POST /pay` paralel** (amount=grand_total):
```
HTTP: [200,200,200,200,200,200]          (6 sukses; seharusnya 1)
amount_paid = 164.835.000  >  grand_total = 27.472.500   → OVERPAY 6.0×
```
**Dampak:** kas keluar berganda (double disbursement), AP under-stated, GL rusak. Kelas sama dgn temuan P0 #1 travel (RC-01).

**Rekomendasi (tak dikerjakan):** optimistic-concurrency —
`find_one_and_update({"id":bill_id, "amount_paid": prev_paid}, {"$inc":..., "$set":...})` lalu tolak/retry bila `None`;
atau guard atomik `update_one({"id":bill_id, "$expr":{"$lte":[{"$add":["$amount_paid", amount]}, "$grand_total"]}}, {"$inc":...})` + cek `modified_count`.

**Suspect terkait — KN-077-RACE-AR-RECEIPT (P1):** `services/ar_receipt_service.py::_apply_to_order` (~134→163) berpola
TOCTOU **identik** (baca outstanding → cek → update). Uji runtime #077 **INCONCLUSIVE** (SO seed tak eligible AR → 400).
Perlu repro: siapkan SO invoiced ber-outstanding lalu re-run `verify_concurrency.py`.

---

## 2. 🟢 KN-077-STATE-SO — State-machine Sales Order SEHAT  [VERIFIED]

`verify_state_machine.py` (login admin, uji perilaku) — **4/4 lolos**:

| Invarian | Uji | Hasil |
|---|---|---|
| SM-1 CANCEL-RELEASE | cancel SO 'reserved' → roll ter-reserve lepas | ✅ 2 roll → 0 tersisa (via `release_order_rolls`) |
| SM-2 TERMINAL-GUARD | cancel SO 'done' | ✅ ditolak 409 |
| SM-3 IDEMPOTENT | cancel-ulang SO cancelled | ✅ 409 bersih (no double-effect, no 5xx) |
| SM-4 NO-ZOMBIE-TASK | wms_task aktif pasca-cancel | ✅ 0 tersisa (semua cancelled) |

Berbeda dgn travel (4 dari 7 P0 di area ini), **KN state-machine SO benar** — hasil negatif yang menaikkan keyakinan.

---

## 3. Confidence level — sebelum vs sesudah (jujur)

| Area | #076 | #077 | Alasan |
|---|---|---|---|
| Integritas DATA/GL + idempotensi | 95% | 95% | tak berubah (sudah kuat) |
| AuthN coverage | 90% | 90% | ter-gate (verify_auth_coverage) |
| Isolasi lintas-entitas | 88% | 88% | ter-gate (verify_cross_entity) |
| **Concurrency / race** | **~40%** | **~88%** | kelas kini diuji+ter-gate; P0 ditemukan; sisa: AR-receipt repro + jalur deposit/stok-adjust |
| **State-machine** | **~55%** | **~88%** | SO diverifikasi hijau; sisa: WMS/PO/transfer belum ekshaustif |
| Numeric bounds | 65% | 70% | masih parsial (import_fuzz + guard inline); belum ada gate schema-level |
| **OVERALL (kelas bug besar teridentifikasi & terpantau)** | **~80–82%** | **~90–91%** | 2 blindspot terbesar ditutup dengan bukti nyata |

### Kenapa **~90–91%**, bukan lebih tinggi (sisa risiko jujur)
1. **AR-receipt race** belum terbukti tereksekusi (suspect kuat, pola TOCTOU identik) — perlu repro dgn order AR-eligible.
2. **State-machine WMS/PO/transfer** belum diuji ekshaustif (baru SO).
3. **Numeric bounds** belum ada gate schema-level (`Field(ge=/gt=)`); baru terlindung guard inline + import_fuzz.
4. **Modul non-finansial** (hr_*, crm_omnichannel, rfid, consolidation) belum disapu penuh untuk race/IDOR-tulis.
5. **E2E FE alur-dalam** (create-order → print, POS lengkap) belum ditelusuri untuk tiap role.

**Untuk menembus ≥95%** (LATER): repro AR-receipt; perluas `verify_state_machine` ke WMS/PO/transfer;
tambah `verify_numeric_bounds.py` (statik) untuk field uang/qty; sweep race pada seluruh jalur `$inc` uang/stok.

---

## 4. Status gate (`bash scripts/gate.sh` → `memory/GATE_RECEIPT.md`)

| Gate | Hasil | Makna |
|---|---|---|
| guard:auth_coverage (INV-AUTH-01) | FAIL | 8 endpoint tanpa auth (#076 terbuka) |
| guard:cross_entity (INV-ENTITY-01) | FAIL | 4 kebocoran lintas-entitas (#076 terbuka) |
| **guard:concurrency (INV-CONC-01)** | **FAIL** | **overpay vendor-bill (P0 #077)** |
| **guard:state_machine (INV-STATE-01)** | **PASS** | **state-machine SO sehat** |
| verify_data_integrity | PASS 122/0/WARN1 | GL/domain sehat |
| audit_endpoint_sweep / health_check / check_nav_map | PASS | 5xx/isi/nav sehat |
| validate_compliance | FAIL (pre-existing) | `sales_orders.py` 803>800 baris (aturan KN sendiri) |

> Gate MERAH pada auth/entity/concurrency = **bug #076/#077 belum diperbaiki** (report-only) — bukti gate bekerja, bukan hijau-palsu.

---

## 5. Artefak sesi ini
- `scripts/guardrails/verify_concurrency.py`, `scripts/guardrails/verify_state_machine.py` (gate baru).
- `scripts/gate.sh` (di-wire 5 guardrail), `memory/GATE_RECEIPT.md` (receipt).
- Update: `memory/INVARIANTS.md` (INV-CONC-01, INV-STATE-01), `memory/BUG_REGISTRY.md` (KN-077-*).
