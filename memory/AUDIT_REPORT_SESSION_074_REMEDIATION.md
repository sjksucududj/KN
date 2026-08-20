# AUDIT REPORT — SESSION #074 · Kampanye "kejar ~90%" (Poin 1–5) + Dossier Perbaikan

> **Mode: AUDIT-ONLY.** Tidak ada satu baris kode aplikasi (`backend/`, `frontend/src/`)
> yang diubah. Diverifikasi via manifest SHA-256 sebelum vs sesudah audit → **identik**
> (`APP CODE UNCHANGED`). Yang ditambahkan hanya artefak forensik (`forensic/fa_s074_*.py`,
> `forensic/fa_import_fuzz.py`, `forensic/fa_landed_cost_value.py`, `forensic/fa_idor_matrix.py`)
> + laporan ini.
>
> **Tujuan laporan ini:** dokumen perbaikan **anti-halusinasi** untuk agent/dev sesi berikutnya.
> Setiap bug memuat: lokasi persis (`file:line` + fungsi + alur pemanggilan), root cause,
> **bukti empiris sesi ini** (perintah + output aktual), Expected vs Actual, **langkah perbaikan
> konkret + snippet patch**, dan cara verifikasi + risiko regresi.
>
> Untuk bug yang sudah pernah diverifikasi (Session ≤073), entri diberi label **[UPDATE]** —
> isinya bukan pengulangan, tapi **pendalaman** (line-level + patch). Temuan asli sesi ini
> diberi label **[BARU]**.

- **Tanggal:** 2026-07-05 · **Basis kode:** clone `github.com/sudahtidakpunyaide/kn`
- **DB:** reseed bersih `seed_realistic.py` sebelum tiap probe destructive.
- **Gate baseline:** `python scripts/verify_data_integrity.py` → **PASS 120 / FAIL 0 / WARN 0**.
- **Layanan:** backend `:8001`, frontend `:3000` — RUNNING.
- **Kredensial uji:** `admin@kainnusantara.id` · `manager@…` · `sales@…` · `warehouse@…` — password **`demo12345`**.
- **Entitas:** `ent_ksc` (PT Kain Suka Cita), `ent_kanda` (PT Kanda …).

---

## 0. Peta koleksi & akun (rujukan agar TIDAK salah nama)

| Konsep | Koleksi Mongo sebenarnya | Catatan |
|---|---|---|
| Entitas legal | **`business_entities`** | *bukan* `entities` |
| Bagan akun | **`gl_accounts`** | *bukan* `accounts`; template `entity_id=None`, per-code global |
| Jurnal | **`journal_entries`** | `lines[].{account_code,debit,credit}`, `total_debit`, `total_credit`, `status`, `entity_id`, `source_type`, `source_id` |
| Stok fisik (SSOT) | `inventory_rolls` | scope pakai `owner_entity_id` |

**Akun kunci** (dari `gl_service.DEFAULT_COA`): `1-1100` Kas/Bank · `1-1200` Piutang ·
`1-1300` Persediaan · `1-1500` PPN Masukan · `2-1100` Hutang Usaha (AP) · `2-1150` GR/IR ·
`2-1200` PPN Keluaran · `3-2900` Ekuitas Saldo Awal · `4-1000` Pendapatan · `5-1000` HPP ·
`5-9000` Beban Angkut Pembelian.

**Fakta arsitektur penting (mempengaruhi diagnosis GL):**
`gl_service.backfill_journals()` dipanggil **saat startup** (`bootstrap.py:1268`) & manual via
`POST /api/gl/...` (`routers/gl.py:161`). Backfill **hanya memposting** `sales_orders`,
`cash_transactions` (status≠void), dan `vendor_bills` (posted/paid) — **tidak pernah membalik
(reverse)** jurnal, dan **tidak menyentuh** `sales_return`, `purchase_return`, `landed_cost`.
Artinya:
- Pembayaran (cash out) yang di-insert langsung ke `cash_transactions` **akan** ter-posting
  di backfill berikutnya (eventually-consistent) → lihat catatan di LC-PAY.
- Retur jual/beli & landed-cost **tidak punya jalur posting sama sekali** → murni hilang.

---

## 1. Cakupan & metode sesi ini (poin 1–5)

| Poin | Fokus | Skrip | Hasil ringkas |
|---|---|---|---|
| #1 | Error-branch sweep menyeluruh + assertion semantik nilai GL | `fa_s074_errorpath.py`, `fa_s074_semantic.py` | 180 rute mutasi `{id}` diprobe → **2×HTTP 500**, **2×200-noop**; JE global & trial-balance **seimbang**; **META-GATE-GL** terbukti buta; **INV-GL-DRIFT** tersingkap |
| #3 | Fuzz import master-data (0% cover) | `fa_import_fuzz.py` | **6 temuan** (injection, 500 non-UTF8, harga negatif/inf, XSS image, clobber SKU) · privilege import aman |
| #4 | Landed-cost & konsolidasi di level NILAI | `fa_landed_cost_value.py` | **LC-APPLY-GL (P1 BARU)** + **LC-PAY-double-count (P2 BARU)** · konsolidasi **balance (bersih)** |
| #2 | Matriks IDOR 2-arah | `fa_idor_matrix.py` | Kebocoran **simetris** 2 arah pada ~7 famili endpoint write |
| #5 | E2E frontend interaksi-dalam | Playwright (screenshot tool) | Import dry-run menerima baris jahat "0 error" → tak ada validasi FE; hanya warning a11y (`DialogTitle`) |

**Cara menjalankan ulang** (semua di `/app`, backend harus RUNNING):
```bash
python seed_realistic.py                       # reset bersih SEBELUM tiap probe destructive
python forensic/fa_s074_semantic.py            # #1 semantik (READ-only + 1 mutasi self-clean)
python forensic/fa_s074_errorpath.py           # #1 error-branch (READ-mostly)
python forensic/fa_import_fuzz.py              # #3 (DESTRUCTIVE → reseed)
python forensic/fa_landed_cost_value.py        # #4 (DESTRUCTIVE → reseed)
python forensic/fa_idor_matrix.py              # #2 (DESTRUCTIVE → reseed)
```

---

## 2. Ringkasan temuan (prioritas perbaikan)

| # | Sev | ID | Status | Judul singkat |
|---|---|---|---|---|
| 1 | 🔴 P0 | **RET-2** | [UPDATE] | Sales-return approve → **credit note & jurnal TIDAK terbentuk** (AttributeError ditelan) |
| 2 | 🔴 P0 | **PRET-GL** | [UPDATE] | Retur beli approve → Nota Debit + stok turun, **0 jurnal GL** (AP & Persediaan tak berubah) |
| 3 | 🔴 P0 | **VB-CANCEL-GL** | [UPDATE] | Cancel vendor-bill **posted** → status cancelled tapi **jurnal AP tidak dibalik** |
| 4 | 🔴 P0 | **IDOR-WRITE** | [UPDATE] | ~7 famili endpoint write bocor **lintas-entitas 2 arah** (mis. `simulate-payment` bikin invoice PT lain) |
| 5 | 🟠 P1 | **LC-APPLY-GL** | [BARU] | Approve landed cost menaikkan HPP roll tapi **tidak posting GL Persediaan** |
| 6 | 🟠 P1 | **META-GATE-GL** | [UPDATE] | CI gate **buta** terhadap keseimbangan jurnal & rekonsiliasi persediaan |
| 7 | 🟡 P2 | **RET-500** | [UPDATE] | `sales-returns/{id}/approve` & `/reject` → **HTTP 500** untuk id tak ada (persis 2 dari 180 rute) |
| 8 | 🟡 P2 | **COGS-ZERO** | [UPDATE] | Penjualan diakui pendapatan tapi **HPP=0** bila cost roll tak diketahui → laba kotor overstated |
| 9 | 🟡 P2 | **LC-PAY-EXPENSE** | [BARU] | Bayar landed cost → backfill sbg **Beban Angkut (5-9000)**, padahal sudah dikapitalisasi ke roll → **double-count** |
| 10 | 🟡 P2 | **IMP-NONUTF8-500** | [BARU] | Import CSV non-UTF8 → **HTTP 500** (UnicodeDecodeError tak ditangani) |
| 11 | 🟡 P2 | **IMP-CSV-INJECTION** | [BARU] | Import simpan formula mentah → **CSV/Formula injection** saat export |
| 12 | 🟡 P2 | **IMP-NEG-PRICE** | [BARU] | Import produk menerima **harga negatif** (tak ada validasi ≥0) |
| 13 | 🟡 P2 | **VAL-UOM** | [UPDATE] | UOM menerima `conversion_to_base` **negatif** |
| 14 | 🔵 P3 | **IMP-IMG-XSS** | [BARU] | Import simpan `javascript:` di field image (tak ada whitelist skema) |
| 15 | 🔵 P3 | **IMP-INF-PRICE** | [BARU] | `1e309` → `inf` tersimpan (rusak agregasi/serialisasi JSON) |
| 16 | 🔵 P3 | **ONBOARD-NOOP** | [BARU] | `POST /onboarding/{task_id}/complete` → **200** untuk task_id ngawur |
| 17 | 🔵 P3 | **RET-ATT-NOOP** | [UPDATE] | `DELETE /sales-returns/{id}/attachments/{att_id}` → **200** walau id ngawur |
| 18 | 🔵 P3 | **FE-A11Y-DIALOG** | [BARU] | `DialogContent` tanpa `DialogTitle` → warning konsol berulang (a11y) |
| 19 | 🔵 P3 | **INV-GL-DRIFT** | [BARU/ops] | Subledger persediaan **Rp 533 jt** vs GL `1-1300` **Rp 750 rb** — lihat catatan jujur |
| 20 | 🔵 P3 | **AUTH-ORDER** | [UPDATE] | 422 (validasi body) mendahului 401 (auth) — perilaku inheren FastAPI |
| — | ⬇️ | **IMP-XENT-CLOBBER** | [KOREKSI] | *Diturunkan* ke observasi P3 — produk memang SHARED by-design (lihat §5) |

---

## 3. DOSSIER PER-BUG (lokasi, root cause, bukti, patch, verifikasi)

---

### 🔴 P0 — RET-2 · Sales-return approve tidak menerbitkan Credit Note / jurnal  [UPDATE]

**Lokasi**
- Fatal: `backend/services/return_service.py:75`
  ```python
  unit_cost = await gl_service._avg_unit_cost(pid, eid)   # ← fungsi ini TIDAK ADA di gl_service
  ```
  Berada di dalam `_create_credit_note_and_post_gl(ret)` (fungsi mulai ±baris 45).
- Pemanggil: `return_service.approve_and_adjust_stock(...)` — memanggil
  `_create_credit_note_and_post_gl` di dalam blok `try/except` (±baris 285–291) yang
  **menelan semua exception** (GL "best-effort").
- Router: `backend/routers/sales_returns.py:154` `approve_return`.

**Root cause (naratif)**
`gl_service` hanya punya `_order_item_unit_cost(order, item)` (`gl_service.py:601`) dan
`costing_service.wac_for_product(...)`. **Tidak ada** `_avg_unit_cost`. Maka baris 75
melempar `AttributeError` **sebelum** `db.credit_notes.insert_one(...)` (baris 112). Exception
naik ke `approve_and_adjust_stock`, ditelan `try/except` → dokumen retur tetap di-set
`status='approved'` + `stock_adjusted=True`, **tetapi** `credit_note_id` tetap `None`, tak ada
row `credit_notes`, tak ada `journal_entries` `source_type='sales_return'`. Jurnal reversal
(Dr Pendapatan/PPN, Cr Piutang; Dr Persediaan, Cr HPP) yang seharusnya dibuat oleh
`gl_service.post_sales_return` (`gl_service.py:914`, fungsi ini SUDAH benar) **tak pernah dicapai**.

**Bukti empiris (sesi ini, DB bersih)**
```
create sales-return -> 201 ; approve -> 200
after approve: status=approved  credit_note_id=None  stock_adjusted=True
credit_notes delta=0   sales_return JE delta=0
```

**Expected vs Actual**

| | Expected | Actual |
|---|---|---|
| Status retur | approved | approved ✔ |
| Stok kembali | ✔ | ✔ |
| Credit Note | 1 dibuat, `credit_note_id` terisi | **0 dibuat**, `credit_note_id=None` |
| Jurnal `sales_return` | 1 (Dr Pendapatan/PPN, Cr Piutang; Dr Persediaan, Cr HPP) | **0** |

**Langkah perbaikan (pilih A — paling minim & sesuai niat API)**

*Fix A — tambah helper yang hilang di `gl_service.py`* (letakkan dekat `_order_item_unit_cost`, ±baris 625):
```python
async def _avg_unit_cost(product_id: str, entity_id: str = "") -> float:
    """WAC per produk (untuk COGS reversal retur). Fallback 0 bila tak ada cost."""
    w = await costing_service.wac_for_product(product_id, entity_id=entity_id or None)
    return float(w.get("wac") or 0)
```
`costing_service` sudah di-import di `gl_service.py:21` → tidak perlu import baru.

*Fix B — alternatif tanpa sentuh gl_service* (ubah `return_service.py:75`):
```python
from services import costing_service   # tambahkan di header import bila belum ada
...
_wac = await costing_service.wac_for_product(pid, entity_id=eid or None)
unit_cost = float(_wac.get("wac") or item.get("unit_cost") or 0)
```

*Fix C — WAJIB dampingi A/B: hentikan penelanan senyap.* Ubah `except Exception:` (baris 119
& ±285) agar **mencatat log** (dan idealnya menaikkan flag di dokumen), sehingga kegagalan GL
tidak lagi tak terlihat:
```python
except Exception as e:                         # noqa: BLE001
    import logging; logging.getLogger("gl").exception("sales_return GL gagal: %s", e)
    je = None
```

**Verifikasi sesudah fix**
```bash
python seed_realistic.py
python - <<'PY'  # atau jalankan ulang blok RET-2 di forensic
# buat sales-return dari SO, approve, lalu cek:
#   db.credit_notes delta == 1  &&  credit_note_id terisi
#   db.journal_entries(source_type='sales_return') delta == 1 && total_debit==total_credit
PY
```
**Risiko regresi:** rendah. Idempotensi dijaga `_already_posted('sales_return', rid)`.
Uji ulang skenario `condition='damaged'` (tidak menambah COGS reversal — perilaku sengaja).

---

### 🔴 P0 — PRET-GL · Retur beli approve tanpa jurnal GL  [UPDATE]

**Lokasi**
- `backend/services/purchase_return_service.py:115` `approve_and_adjust_stock(...)`.
  - Baris 142–147: terbitkan `debit_note_number`, set `status='approved'`.
  - Baris 150–156: hanya `$inc purchase_orders.returned_amount` + `recompute_po_payment_status`.
  - **Tidak ada** panggilan `gl_service.*` di seluruh fungsi.
- Router: `backend/routers/purchase_returns.py` (approve).

**Root cause**
Retur beli adalah kebalikan Goods-Receipt/Vendor-Bill, tapi tak ada fungsi GL untuk itu.
`gl_service` punya `post_goods_receipt` (Dr `1-1300`/Cr `2-1150`, baris 862) dan
`post_vendor_bill` (Dr `2-1150`+`1-1500`/Cr `2-1100`, baris 876) — **tidak ada**
`post_purchase_return`. Maka nilai retur tidak mengurangi Hutang (`2-1100`) maupun Persediaan
(`1-1300`) di GL.

**Bukti empiris (sesi ini, via `fa_coverage_gap.py`)**
```
Retur beli approve -> Nota Debit DN-00001 terbit + stok turun
GL Hutang(2-1100) Δ = 0 ; GL Persediaan(1-1300) Δ = 0 ; JE purchase_return = 0
```

**Expected vs Actual**

| | Expected (barang balik ke supplier, AP berkurang) | Actual |
|---|---|---|
| Nota Debit | terbit | terbit ✔ |
| Stok | turun | turun ✔ |
| Jurnal | Dr `2-1100` Hutang / Cr `1-1300` Persediaan (+ Cr `1-1500` PPN Masukan bila ada) | **0** |

**Langkah perbaikan**

1) Tambah fungsi di `gl_service.py` (model dari `post_goods_receipt`, idempotent):
```python
async def post_purchase_return(ret: Dict[str, Any], *, amount: float,
                               ppn: float = 0.0, label: str = "") -> Optional[Dict[str, Any]]:
    """Retur beli → balik GRIR/hutang & persediaan. Idempotent (source_type='purchase_return')."""
    rid = ret.get("id"); amount = round(float(amount or 0), 2)
    if not rid or amount <= EPS or await _already_posted("purchase_return", rid):
        return None
    await seed_default_coa()
    net = round(amount - round(float(ppn or 0), 2), 2)
    lines = [{"account_code": ACC_HUTANG, "debit": amount, "credit": 0.0,
              "description": f"Retur beli {label} (Nota Debit)"}]
    lines.append({"account_code": ACC_PERSEDIAAN, "debit": 0.0, "credit": net,
                  "description": f"Barang keluar retur beli {label}"})
    if ppn and ppn > EPS:
        lines.append({"account_code": ACC_PPN_IN, "debit": 0.0, "credit": round(ppn, 2),
                      "description": f"Reversal PPN Masukan {label}"})
    return await _insert_entry(lines=lines, description=f"Retur beli {label}",
        date=ret.get("approved_at") or now_iso(), source_type="purchase_return",
        source_id=rid, entity_id=ret.get("entity_id", ""), created_by="system", source_label=label)
```
> Catatan akuntansi: jika Vendor Bill BELUM di-posting (hutang belum diakui), lawan debit yang
> lebih tepat adalah `2-1150` GR/IR, bukan `2-1100`. Tentukan berdasarkan `ret.po_id` →
> apakah ada `journal_entries(source_type='vendor_bill', ...)` untuk PO itu. Sederhananya:
> pakai `ACC_HUTANG` bila bill sudah posted, `ACC_GRIR` bila belum.

2) Panggil di `purchase_return_service.approve_and_adjust_stock`, setelah blok baris 150–156:
```python
from services import gl_service
await gl_service.post_purchase_return(
    await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}),
    amount=float(ret.get("total_amount", 0)), ppn=float(ret.get("ppn_amount", 0) or 0),
    label=debit_note)
```

**Verifikasi:** `python forensic/fa_coverage_gap.py` → bagian PRET harus menunjukkan
`GL Hutang Δ = -total` (atau GRIR) dan `Persediaan Δ = -net`, JE seimbang.
**Regresi:** cek `recompute_po_payment_status` tidak bentrok (returned_amount vs jurnal).

---

### 🔴 P0 — VB-CANCEL-GL · Cancel vendor-bill *posted* tanpa reversal  [UPDATE]

**Lokasi**
- `backend/routers/vendor_bills.py:438` `cancel_vendor_bill(...)`.
  - Baris 447 hanya memblok status `cancelled`/`paid` → status **`posted`** (belum dibayar)
    **boleh** dibatalkan.
  - Baris 449–454: set `status='cancelled'` + timeline. **Tak ada reversal jurnal.**
- Jurnal saat posted dibuat oleh `gl_service.post_vendor_bill` (`gl_service.py:876`):
  Dr `2-1150` GR/IR (+ Dr `1-1500` PPN Masukan) / Cr `2-1100` Hutang.

**Root cause**
Backfill tak pernah membalik jurnal; cancel hanya ubah status. Maka JE vendor_bill dari saat
posted tetap ada → Hutang `2-1100` tetap ter-kredit walau bill dibatalkan.

**Bukti empiris (sesi ini)**
```
Bill VB-00001 posted -> GL Cr Hutang(2-1100) = -27.472.500
cancel -> status=cancelled ; GL Hutang Δ = 0 ; JE reversal = 0
```

**Expected vs Actual**

| | Expected | Actual |
|---|---|---|
| Status | cancelled | cancelled ✔ |
| Jurnal balik | 1 reversal (Dr `2-1100` / Cr `2-1150`+`1-1500`) | **0** |
| Saldo Hutang | kembali seperti sebelum posted | tetap ter-kredit ❌ |

**Langkah perbaikan**

1) Tambah reverser di `gl_service.py` (model dari `reverse_order_journals`, baris 832):
```python
async def reverse_vendor_bill(bill: Dict[str, Any], reason: str = "",
                              actor_name: str = "system") -> Optional[Dict[str, Any]]:
    bid = bill.get("id")
    if not bid or await _already_posted("vendor_bill_reversal", bid):
        return None
    je = await db.journal_entries.find_one(
        {"source_type": "vendor_bill", "source_id": bid, "status": {"$ne": "void"}}, {"_id": 0})
    if not je:
        return None
    lines = [{"account_code": l["account_code"],
              "debit": float(l.get("credit", 0) or 0), "credit": float(l.get("debit", 0) or 0),
              "description": f"Reversal: {l.get('description','')}".strip()} for l in je["lines"]]
    rev = await _insert_entry(lines=lines,
        description=f"Reversal {je.get('number')} — {reason or 'bill dibatalkan'}",
        date=now_iso(), source_type="vendor_bill_reversal", source_id=bid,
        entity_id=je.get("entity_id",""), created_by=actor_name, source_label=je.get("source_label",""))
    await db.journal_entries.update_one({"id": je["id"]},
        {"$set": {"reversed": True, "reversal_id": rev["id"], "updated_at": now_iso()}})
    return rev
```
2) Di `cancel_vendor_bill`, sebelum/segera setelah set cancelled (±baris 449):
```python
if bill.get("status") == "posted":
    from services import gl_service
    await gl_service.reverse_vendor_bill(bill, reason=payload.notes or "", actor_name=actor["name"])
```
> Alternatif kebijakan: **larang** cancel bill `posted` (ubah baris 447 → tambah `"posted"`),
> arahkan user ke jalur credit-note/retur beli. Reversal tetap lebih benar utuh.

**Verifikasi:** post bill → cancel → `GL Hutang Δ = 0` **net** (posting + reversal saling hapus),
ada 2 JE (`vendor_bill` + `vendor_bill_reversal`), keduanya seimbang.
**Regresi:** `reject_vendor_bill` (baris 362) menset cancelled untuk `pending_approval`
(belum posted → tak perlu reversal) — jangan ikut di-reverse.

---

### 🔴 P0 — IDOR-WRITE · Kebocoran write lintas-entitas (2 arah)  [UPDATE]

**Lokasi & pola**
Endpoint write mengambil dokumen **tanpa** memanggil `assert_entity_access(doc, coll, ctx)`
(helper ada di `backend/entity_scope.py:151`, sudah dipakai benar di endpoint GET, mis.
`sales_returns.py:124`). Endpoint write men-skip cek ini → user yang di-scope hanya ke entitas A
bisa memutasi dokumen milik entitas B.

**Matriks 2-arah (sesi ini, `fa_idor_matrix.py`)** — arah A = user KSC → dok KANDA, arah B = user KANDA → dok KSC. Kebocoran **simetris**:

| Endpoint (pola) | Arah A | Arah B | Klasifikasi |
|---|---|---|---|
| `PATCH /sales-orders/{id}` | 200 | 200 | LEAK (edit) |
| `POST /sales-orders/{id}/simulate-payment` | 200 | 200 | **LEAK — bikin invoice PT lain** (INV-0002-01/INV-0001-01) |
| `POST /sales-orders/{id}/submit-for-approval` | 409 | 409 | LEAK-REACHED (logika jalan) |
| `POST /sales-orders/{id}/cancel` | 409 | 409 | LEAK-REACHED |
| `POST /sales-returns/{id}/submit` | 200/400 | 200/400 | LEAK |
| `POST /wms/tasks/{id}/advance` | 200 | 200 | LEAK |
| `POST /inbound/rolls/{id}/inspect` | 200 | 200 | LEAK |
| `PATCH /special-orders/{id}` | (no doc) | 400 | LEAK-REACHED |

**Terbukti TERLINDUNG (untuk kalibrasi):**
`POST /sales-orders/{id}/request-special-price` → **404** (sudah entity-scoped);
`PATCH /price-approvals/{id}` → **403** (dilindungi kepemilikan/ownership, bukan entitas).

**Root cause**
Guard anti-IDOR hanya konsisten di jalur baca. Jalur tulis mengandalkan `{"id": ...}` global
tanpa memfilter/menegakkan `allowed_entity_ids`.

**Langkah perbaikan (pola seragam)** — untuk **setiap** endpoint write pada koleksi ter-scope,
setelah `find_one`:
```python
from entity_scope import entity_ctx, assert_entity_access
ctx = await entity_ctx(request)
doc = await db.sales_orders.find_one({"id": order_id})
if not doc:
    raise HTTPException(status_code=404, detail="Data tidak ditemukan")
doc.pop("_id", None)
assert_entity_access(doc, "sales_orders", ctx)   # 404 bila lintas-entitas
```
Terapkan pada handler yang bocor di tabel di atas (ganti nama koleksi sesuai konteks:
`sales_orders`, `special_orders`, `sales_returns`, `wms_tasks`, `inventory_rolls`).
> Untuk `simulate-payment`: ini yang paling berbahaya (membuat `tax_invoices`/invoice pada PT
> lain). Prioritaskan.

**Verifikasi:** `python forensic/fa_idor_matrix.py` → semua baris LEAK/LEAK-REACHED harus
berubah jadi `PROTECTED*(404)`. **Regresi:** pastikan admin/manager (cross-entity, `view_all`)
tetap bisa; `assert_entity_access` memakai `allowed_entity_ids` sehingga role lintas-entitas aman.

---

### 🟠 P1 — LC-APPLY-GL · Landed cost tak posting GL Persediaan  [BARU]

**Lokasi**
- `backend/routers/landed_cost.py` `approve_landed_cost` → `landed_cost_service.apply_allocation_to_rolls(...)`.
- `backend/services/landed_cost_service.py`: `apply_allocation_to_rolls` hanya
  `db.inventory_rolls.update_one(..., {"$inc": {"unit_cost": ..., "landed_cost_total": ...}})`.
  **Tidak ada** panggilan `gl_service.*`.

**Root cause**
Biaya landed cost dikapitalisasi ke **HPP roll** (subledger) tetapi tidak diakui di GL — tak ada
Dr `1-1300` Persediaan / Cr `2-1100` (atau clearing). GL Persediaan jadi understated vs fisik.

**Bukti empiris (sesi ini, `fa_landed_cost_value.py`)**
```
allocated_total = 5.000.000
GL 1-1300         : 750.000 -> 750.000   (Δ = 0)
physical roll val : X -> X+5.000.000     (Δ = +5.000.000)
journal_entries source=landed_cost : 0 -> 0
```

**Expected vs Actual**

| | Expected | Actual |
|---|---|---|
| HPP roll | naik +alloc | naik ✔ |
| GL `1-1300` | naik +alloc | **Δ 0** ❌ |
| Jurnal | Dr `1-1300` / Cr `2-1100` (atau clearing landed-cost) | **0** |

**Langkah perbaikan**
1) `gl_service.py` — fungsi baru (idempotent `source_type='landed_cost'`):
```python
async def post_landed_cost(voucher: Dict[str, Any], *, amount: float,
                           label: str = "") -> Optional[Dict[str, Any]]:
    vid = voucher.get("id"); amount = round(float(amount or 0), 2)
    if not vid or amount <= EPS or await _already_posted("landed_cost", vid):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_PERSEDIAAN, ACC_HUTANG, amount,   # Dr Persediaan / Cr Hutang(clearing)
                           f"Kapitalisasi landed cost {label}")
    return await _insert_entry(lines=lines, description=f"Landed cost {label}", date=now_iso(),
        source_type="landed_cost", source_id=vid, entity_id=voucher.get("entity_id",""),
        created_by="system", source_label=label)
```
2) Panggil di `approve_landed_cost` setelah `apply_allocation_to_rolls`, dengan
`amount = Σ alloc_amount` (total teralokasi).

**Verifikasi:** `python forensic/fa_landed_cost_value.py` → `GL 1-1300 Δ == allocated_total`,
1 JE `landed_cost` seimbang. **Regresi:** koordinasikan dengan LC-PAY (di bawah) agar tidak double.

---

### 🟠 P1 — META-GATE-GL · Gate integritas buta terhadap balance jurnal  [UPDATE]

**Lokasi**: `scripts/verify_data_integrity.py`.

**Root cause (grep sesi ini)**: tidak ada referensi ke `total_debit/total_credit`,
`trial_balance`, "neraca saldo", maupun rekonsiliasi persediaan.

**Bukti empiris (mutation test, `fa_s074_semantic.py`)**
```
gate source references to JE-balance/trial-balance: NONE
[inject] journal_entries: debit 1000 != credit 1 (status posted)
gate exit=0 green=True  -> "SEMUA INVARIAN VALID"  (JE tak seimbang LOLOS)
[cleanup] synthetic unbalanced JE removed
```
Inilah alasan RET-2/PRET-GL/VB-CANCEL-GL/LC-APPLY-GL semuanya lolos CI: gate tak pernah
mengecek keseimbangan/rekonsiliasi.

**Langkah perbaikan** — tambahkan 3 invarian ke `verify_data_integrity.py`:
```python
# INV-GL-1: setiap JE posted seimbang
bad = [je["number"] async for je in db.journal_entries.find({"status":"posted"})
       if round(sum(l.get("debit",0) for l in je["lines"]),2)
          != round(sum(l.get("credit",0) for l in je["lines"]),2)]
assert not bad, f"JE tidak seimbang: {bad[:10]}"

# INV-GL-2: trial balance seimbang per entitas
for eid in entity_ids:
    tb = await gl_service.trial_balance(scope={"entity_id": eid})
    assert tb["balanced"], f"Trial balance {eid} tidak balance"

# INV-GL-3 (WARN, bukan FAIL): rekonsiliasi persediaan
recon = await gl_service.inventory_reconciliation()
for r in recon["rows"]:
    warn_if(abs(r["difference"]) > TOLERANSI, f"Drift persediaan {r['entity_id']}={r['difference']}")
```
**Verifikasi:** ulangi mutation → gate sekarang **FAIL**. **Catatan:** INV-GL-3 sebaiknya WARN
selama INV-GL-DRIFT (§ P3) belum di-true-up, agar tidak memerahkan gate karena artefak seed.

---

### 🟡 P2 — RET-500 · approve/reject sales-return 500 utk id tak ada  [UPDATE]

**Lokasi**: `backend/routers/sales_returns.py:154` `approve_return` & `:173` `reject_return`.
Keduanya langsung memanggil `return_service.approve_and_adjust_stock` / `reject_return`, yang
`raise ValueError("Retur tidak ditemukan")` (return_service). Router **tak menangkap** →
FastAPI balas **HTTP 500**.

**Bukti (sweep menyeluruh, `fa_s074_errorpath.py`)**
```
total 180 rute mutasi /{id} diprobe dgn id ngawur
  proper 4xx : 176
  500 CRASHES: 2  ->  POST /api/sales-returns/{id}/approve , POST /api/sales-returns/{id}/reject
  200 noop   : 2  (lihat ONBOARD-NOOP & RET-ATT-NOOP)
```
(Mengoreksi kecurigaan lama "ValueError→500 di 79 endpoint": **hanya 2**.)

**Langkah perbaikan** — jadikan **satu** dengan fix IDOR sales-returns: ambil dokumen dulu di
router, 404 bila tak ada, `assert_entity_access`, baru panggil service:
```python
@router.post("/sales-returns/{return_id}/approve")
async def approve_return(return_id: str, request: Request, payload: SalesReturnDecision = SalesReturnDecision()):
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    doc = await db.sales_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    doc.pop("_id", None); assert_entity_access(doc, "sales_returns", ctx)
    result = await return_service.approve_and_adjust_stock(return_id=return_id,
                approved_by=user.get("name", user.get("email","")), notes=payload.notes)
    ...
```
Terapkan sama pada `reject_return` & `submit_return` (submit sudah 404, tapi belum
`assert_entity_access` — tambahkan). **Verifikasi:** ulang `fa_s074_errorpath.py` → 0 crash.

---

### 🟡 P2 — COGS-ZERO · HPP 0 saat cost roll tak diketahui  [UPDATE]

**Lokasi**: `gl_service.post_order_cogs` (`gl_service.py:627`) + `_order_item_unit_cost` (`:601`).
Baris 645–646: `if total_cogs <= EPS: return None` → bila semua cost 0, **tak ada** JE HPP,
padahal `post_sales_order` tetap mengakui **pendapatan**.

**Bukti empiris (sesi ini, level konsolidasi)**
```
Konsolidasi: revenue = 87.813.750 ; cogs = 0 ; gross_profit = revenue  (margin 100%)
```

**Root cause**: rantai cost `_order_item_unit_cost` (roll aktual → snapshot `item.unit_cost` →
WAC) menghasilkan 0 bila roll/produk tak ber-cost. Karena skip senyap, laba kotor overstated.

**Langkah perbaikan**
- Minimal: bila `_revenue_eligible(order)` **True** tapi `total_cogs<=EPS`, **jangan diam** —
  catat WARN + tandai order `cogs_unknown=True` untuk ditinjau, atau posting HPP memakai WAC
  fallback global; jangan biarkan margin 100% lolos.
- Struktural: jamin roll dari receiving punya `unit_cost` (dari Vendor Bill/PO), atau isi
  `item.unit_cost` snapshot saat SO confirm.
- Tambahkan invarian gate: order revenue-eligible dengan `sales_order` JE ada TAPI tanpa
  `sales_cogs` JE → WARN.

**Verifikasi:** setelah data cost benar, `post_order_cogs` menghasilkan JE Dr `5-1000`/Cr `1-1300`;
konsolidasi menampilkan `cogs > 0`.

---

### 🟡 P2 — LC-PAY-EXPENSE · Pembayaran landed cost jadi beban → double-count  [BARU]

**Lokasi**: `landed_cost_service.pay_landed_cost` meng-`insert` `db.cash_transactions`
(`ref_type='landed_cost'`) langsung. Saat `backfill_journals` berjalan (startup/manual),
`gl_service.post_cash_transaction` memetakan `ref_type='landed_cost'` → contra **`5-9000` Beban
Angkut Pembelian** (`gl_service.py:980-981`).

**Root cause / dampak**
Landed cost sudah dikapitalisasi ke HPP roll (akan mengalir ke `5-1000` HPP saat barang dijual).
Bila pembayaran juga masuk `5-9000` (beban), biaya freight **diakui dua kali**: (a) sebagai Beban
Angkut sekarang, dan (b) sebagai HPP lebih tinggi nanti. Kalau LC-APPLY-GL sudah difix
(kapitalisasi ke `1-1300` via `2-1100`), maka pembayaran seharusnya **Dr `2-1100` / Cr Kas**,
bukan Dr `5-9000`.

**Bukti empiris (sesi ini)**
```
pay LC -> cash_transaction +1 ; journal_entries terkait langsung = 0 (posting tertunda ke backfill)
```

**Langkah perbaikan (koordinasi dengan LC-APPLY-GL)**
- Setelah LC-APPLY-GL memakai clearing `2-1100`: ubah mapping contra untuk `ref_type='landed_cost'`
  di `post_cash_transaction` menjadi `ACC_HUTANG` (`2-1100`) — bukan `ACC_LANDED` — agar pembayaran
  **melunasi hutang landed cost**, bukan menambah beban.
  ```python
  elif ref_type == "landed_cost":
      contra = ACC_HUTANG        # semula ACC_LANDED (5-9000) → double-count bila dikapitalisasi
  ```
- Alternatif kebijakan (expense, bukan kapitalisasi): jangan `$inc unit_cost` roll di
  `apply_allocation_to_rolls`, dan biarkan `5-9000`. Pilih **satu** perlakuan konsisten.
- Tambahkan pemanggilan `gl_service.post_cash_transaction(cash_doc)` **inline** setelah insert
  (seperti `invoices.py:101`) agar GL tak tergantung backfill.

**Verifikasi:** setelah approve+pay LC lalu `POST /api/gl backfill`, tidak ada beban `5-9000`
untuk voucher yang dikapitalisasi; `2-1100` bertambah lalu berkurang oleh pembayaran.

---

### 🟡 P2 — IMP-NONUTF8-500 · Import CSV non-UTF8 → 500  [BARU]

**Lokasi**: `backend/routers/admin.py` → `_parse_csv_or_xlsx(...)`:
`content.decode("utf-8-sig")` tanpa try/except.

**Bukti empiris**
```
POST /api/master-data/import-products (bytes: \xff\xfe...) -> HTTP 500
```
**Fix**:
```python
try:
    text = content.decode("utf-8-sig")
except UnicodeDecodeError:
    raise HTTPException(status_code=400, detail="File bukan UTF-8. Simpan ulang sebagai CSV UTF-8.")
```
(Untuk XLSX: bungkus `openpyxl.load_workbook` dengan try/except → 400, dan batasi ukuran file
untuk cegah zip-bomb.) **Verifikasi:** ulang `fa_import_fuzz.py` T2 → 400, bukan 500.

---

### 🟡 P2 — IMP-CSV-INJECTION · Formula tersimpan mentah → injection saat export  [BARU]

**Lokasi**: `admin.py` import (`_validate_and_enrich_product/customer/...`) menyimpan `name/sku`
apa adanya; `export-products` menuliskannya kembali tanpa escaping.

**Bukti empiris**
```
import name = "=cmd|' /C calc'!A0"  -> tersimpan mentah
export-products -> echoed_in_export = True  (formula ikut, tanpa prefix pengaman)
```
**Fix (defense-in-depth):**
- Saat **export** CSV, escape sel yang diawali `= + - @ TAB CR`: prefiks dengan `'` (apostrof)
  atau bungkus `"\t"+value`.
  ```python
  def _csv_safe(v):
      s = "" if v is None else str(v)
      return ("'" + s) if s[:1] in ("=","+","-","@","\t","\r") else s
  ```
- Saat **import**, tolak/normalisasi nama yang jelas formula bila konteks bisnis tak butuh.

**Verifikasi:** ulang T1 → `echoed_in_export` bernilai nilai ter-escape (`'=...`).

---

### 🟡 P2 — IMP-NEG-PRICE · Harga negatif diterima  [BARU]

**Lokasi**: `admin.py` `_validate_and_enrich_product` — `price = float(row.get("price"))` tanpa
validasi `>= 0` / `isfinite`.
**Bukti**: `AUDITNEG price = -5000.0` tersimpan.
**Fix**:
```python
import math
price = float(row.get("price") or 0)
if not math.isfinite(price) or price < 0:
    errors.append(f"Baris {i}: harga tidak valid ({row.get('price')})"); continue
```
(Sekaligus menutup **IMP-INF-PRICE** — `1e309`→`inf` ter-blok oleh `math.isfinite`.)
**Verifikasi:** ulang T3 → baris negatif/inf masuk `errors`, tidak tersimpan.

---

### 🟡 P2 — VAL-UOM · conversion_to_base negatif diterima  [UPDATE]

**Lokasi**: endpoint UOM create/update (`routers/admin.py` / schema UOM).
**Bukti**: `conversion_to_base = -5` → tersimpan (fa_coverage_gap.py: "UOM menerima conversion_to_base negatif").
**Fix**: validasi `conversion_to_base > 0` di schema Pydantic (`gt=0`) atau di handler:
```python
if float(payload.conversion_to_base or 0) <= 0:
    raise HTTPException(status_code=422, detail="conversion_to_base harus > 0")
```
**Verifikasi:** POST UOM dgn -5 → 422.

---

### 🔵 P3 — IMP-IMG-XSS · image `javascript:` tersimpan  [BARU]
`admin.py` menyimpan `image` mentah. Bukti: `image="javascript:alert(document.cookie)"` tersimpan.
**Fix**: whitelist skema saat import: hanya `http/https` (atau path relatif). Tolak lainnya.
Frontend juga harus tidak me-render URL non-http sebagai `href/src`.

### 🔵 P3 — IMP-INF-PRICE  [BARU]
Ditutup oleh fix IMP-NEG-PRICE (`math.isfinite`). Bukti: `AUDITBIG price=inf`.

### 🔵 P3 — ONBOARD-NOOP · complete task_id ngawur → 200  [BARU]
**Lokasi**: `backend/routers/onboarding.py` `complete_task` — `$addToSet` `completed` dengan
`upsert`, tanpa validasi terhadap katalog task.
**Bukti**: `POST /api/onboarding/BOGUS_AUDIT_ID/complete` → **200**.
**Fix**: validasi `task_id` ∈ daftar task onboarding yang dikenal → 404 bila tidak.

### 🔵 P3 — RET-ATT-NOOP · delete attachment id ngawur → 200  [UPDATE]
**Lokasi**: `sales_returns.py:248` `delete_attachment` — `update_one` tanpa cek `matched_count`.
**Bukti**: `DELETE /api/sales-returns/BOGUS/attachments/BOGUS` → **200 `{ok:true}`**.
**Fix**: fetch return dulu (404 bila tak ada) + `assert_entity_access`; cek attachment ada
(404 bila tidak); baru soft-delete.

### 🔵 P3 — FE-A11Y-DIALOG · DialogContent tanpa DialogTitle  [BARU]
**Bukti (Playwright, sesi ini)**: warning konsol berulang
`` `DialogContent` requires a `DialogTitle` … ``. Non-fungsional (a11y screen-reader).
**Fix**: tambahkan `DialogTitle` (bisa `VisuallyHidden`) di komponen dialog Radix terkait
(mis. Command Palette / modal). **Bukan** white-screen; app tetap jalan.

### 🔵 P3/ops — INV-GL-DRIFT · Subledger persediaan ≫ GL 1-1300  [BARU · dengan koreksi jujur]
**Bukti (sesi ini)**: `ent_ksc` subledger `Rp 533.712.500` vs GL `1-1300` `Rp 750.000`
→ selisih `Rp 532.962.500`.
**Koreksi jujur — ini BUKAN bug alur receiving.** Alur receiving asli **sudah** memposting GL:
`post_goods_receipt` dipanggil di `routers/inbound_receiving.py:464` (Dr `1-1300`/Cr `2-1150`).
Penyebab drift: **`seed_realistic.py` meng-insert rolls langsung** (bypass GL) dan
`post_inventory_opening_balance` (`gl_service.py:1345`) tidak pernah dijalankan otomatis.
**Rekomendasi**: (a) jalankan `post_inventory_opening_balance` sekali setelah seed / di bootstrap
untuk true-up saldo awal; (b) jadikan `inventory_reconciliation` sebagai **WARN** di gate
(INV-GL-3). Relevan karena LC-APPLY-GL & retur akan menambah drift bila tak difix.

### 🔵 P3 — AUTH-ORDER  [UPDATE]
422 (validasi body Pydantic) mendahului 401 (auth). Perilaku **inheren FastAPI** (body divalidasi
sebelum dependency auth pada beberapa pola). **Bukan bug**; bila ingin 401 dulu, pindahkan auth ke
`Depends(require_permission)` sebagai parameter dependency (bukan `await` di dalam body).

---

## 4. Terbukti BERSIH sesi ini (hasil NEGATIF — untuk kepercayaan)

- **Keseimbangan jurnal**: seluruh `journal_entries` posted di DB bersih **seimbang**
  (`Σdebit==Σcredit`, `total_debit==total_credit`) — 0 tak seimbang.
- **Trial balance per entitas**: `ent_ksc` & `ent_kanda` seimbang.
- **Konsolidasi (level nilai)**: `assets 93.713.000 = liab 8.613.000 + equity 85.100.000`,
  gap **0.00** → persamaan akuntansi konsolidasi terpenuhi (bukan bug).
- **Error-branch**: 176 dari 180 rute mutasi `{id}` mengembalikan 4xx yang benar untuk id ngawur.
- **Privilege import**: role `sales` **ditolak 403** pada `import-products` — tak ada eskalasi
  (import = admin-only, sesuai `permissions_config.py`).
- **Validasi jurnal manual** (`create_manual_entry`): tolak baris negatif, dua-sisi, & tak seimbang.
- **Void guard** (`void_entry`): tolak void ganda & void jurnal otomatis.
- **IC-transfer guard**: `src==dst` di-skip anggun (`post_intercompany_transfer`).
- **Payroll GL** (`post_payroll_run`): seimbang (guard `abs(Dr-Cr) > 0.5 → raise`).
- **Frontend**: login→dashboard render, Command-Palette navigasi, import dry-run render hasil,
  submit form berjalan — **tanpa white-screen/crash**; satu-satunya warning = a11y `DialogTitle`.

---

## 5. Koreksi & penurunan klaim (jujur, anti-halusinasi)

- **IMP-XENT-CLOBBER → diturunkan ke P3/observasi.** `products` di `entity_scope.SCOPE_FIELD`
  bernilai **`SHARED`** (katalog SKU sengaja lintas-entitas). Jadi import men-*overwrite* SKU yang
  sama **secara desain**, bukan pelanggaran isolasi entitas. Yang tetap layak diperbaiki: import
  menimpa `name/price` SKU eksisting **tanpa** menampilkan diff nilai lama / audit perubahan.
- **"ValueError→500 di 79 endpoint"** (kecurigaan lama) → terbukti **hanya 2** (RET-500).
- **AUTH-ORDER** → perilaku inheren FastAPI, **bukan bug**.
- **INV-GL-DRIFT** → **bukan** bug alur receiving (alur sudah posting GL). Ini artefak seed + gate
  yang tak merekonsiliasi.
- **VB-PAY & backfill** → pembayaran vendor-bill **benar** (backfill memetakan `ref_type=vendor_bill`
  → Dr `2-1100`/Cr Kas). Tidak dilaporkan sebagai bug.

---

## 6. Urutan perbaikan yang disarankan (fix order)

1. **META-GATE-GL** dulu (tambah 3 invarian) — supaya semua fix GL berikutnya **terbukti** oleh gate.
2. **RET-2** (1 baris + helper) & **RET-500** (1 pola router) — cepat, dampak tinggi, saling terkait.
3. **PRET-GL**, **VB-CANCEL-GL**, **LC-APPLY-GL** + **LC-PAY-EXPENSE** — keluarga GL; kerjakan
   bersama agar perlakuan konsisten (kapitalisasi vs beban) & idempotensi terjaga.
4. **IDOR-WRITE** — pola `assert_entity_access` seragam; prioritas `simulate-payment`.
5. **Import hardening** (NONUTF8, INJECTION, NEG/INF, IMG-XSS) — satu berkas `admin.py`.
6. **VAL-UOM**, **ONBOARD-NOOP**, **RET-ATT-NOOP**, **FE-A11Y-DIALOG** — sisa P2/P3.
7. **INV-GL-DRIFT** — jalankan true-up + jadikan WARN.

Setiap fix wajib disertai: reseed → jalankan skrip forensik terkait → gate hijau (dengan invarian baru).

---

## 7. Tingkat keyakinan (jujur)

- **~90–92%** untuk "semua **kelas** bug besar teridentifikasi" (GL-posting gaps, IDOR write,
  input-validation/import, error-branch, gate-blindness) — naik dari ~88% (S073) karena poin
  1–5 kini tertutup empiris.
- **~72–78%** untuk "semua bug (termasuk edge kecil) tertangkap". Yang masih tipis:
  assertion semantik nilai pada 417 endpoint "hit" belum 100% (baru famili finansial inti),
  branch-coverage angka absolut belum diukur ulang (fokus sesi ini = temuan, bukan angka %),
  dan E2E FE interaksi-dalam baru menyentuh alur import (bukan seluruh alur retur/void di UI).

---

## 8. Lampiran — artefak sesi ini

```
forensic/fa_s074_semantic.py        # #1 assertion semantik + META-GATE mutation (self-clean)
forensic/fa_s074_errorpath.py       # #1 sweep 180 rute mutasi {id}
forensic/fa_import_fuzz.py          # #3 fuzz import master-data
forensic/fa_landed_cost_value.py    # #4 landed-cost & konsolidasi level nilai
forensic/fa_idor_matrix.py          # #2 matriks IDOR 2-arah
forensic/_audit_s074/baseline_appcode.sha256   # manifest AUDIT-ONLY (bukti kode app tak berubah)
memory/AUDIT_REPORT_SESSION_074_REMEDIATION.md # laporan ini
```
Skrip reuse dari sesi lampau yang dipakai ulang untuk grounding: `fa_coverage_gap.py`,
`fa_edge_branches.py`, `scripts/verify_data_integrity.py`.
