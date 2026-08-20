# HANDOFF — Document & PDF Platform (Kain Nusantara ERP)

> **Untuk agent berikutnya.** Dokumen ini adalah titik-mulai (SSOT) untuk melanjutkan
> pengembangan **Document/PDF Platform + E‑Sign + WhatsApp**. Baca dari atas ke bawah.
> Bahasa komunikasi ke user: **Bahasa Indonesia**.
>
> Dibuat: sesi handoff. Status ringkas: **Fase 1 SELESAI, Fase 2 SELESAI di-scaffold namun
> ADA 1 BUG P0 yang SUDAH DIDIAGNOSIS + fix pastinya sudah diverifikasi (lihat §1).**

---

## 0. TL;DR — Mulai Dari Sini (3 langkah)

1. **Terapkan fix P0** di `backend/services/pdf_engine.py` (lihat §1). 1 baris, 2 lokasi.
   Ini meng-unblock seluruh platform.
2. **Verifikasi** endpoint render PDF (§1.3 — curl / python). Harus keluar `%PDF`, HTTP 200.
3. **Lanjut Fase 3 → 7** sesuai `/app/plan.md` (§4 memberi urutan & catatan tiap fase).

Health saat ini:
- Backend ERP: **SEHAT** (hanya endpoint baru `/api/pdf/render/*` yang 500 karena bug di §1).
- Frontend: **SEHAT**.
- Mock/simulasi: **WhatsApp provider** (simulasi, menunggu credential Meta), **E‑Sign OTP** (via log).

---

## 1. 🔴 BUG P0 — HTTP 500 di `/api/pdf/render/{doc_type}/{id}` (SUDAH DIDIAGNOSIS)

### 1.1 Gejala
`GET /api/pdf/render/sales_order/so_007?format=pdf` → **HTTP 500** `"Gagal render dokumen: ..."`.
Traceback tidak muncul di `backend.err.log` karena exception di-catch di router lalu dibungkus
jadi `HTTPException(500)` (lihat `routers/pdf.py` baris ~70-75).

### 1.2 Akar Masalah (ROOT CAUSE — sudah dikonfirmasi via reproduksi)
File: **`/app/backend/services/pdf_engine.py`** → di dalam string `MASTER_TEMPLATE` (Jinja2).

Template memakai `doc.items` di 2 tempat:
```jinja
{% if doc.columns and doc.items %}          <!-- file line ~132 -->
{% for it in doc.items %}...{% endfor %}    <!-- file line ~136 -->
```
`doc` adalah **dict** Python. Di Jinja2, `doc.items` di-resolve dengan **getattr lebih dulu**,
sehingga mengembalikan **method bawaan `dict.items`** (bukan value key `"items"`).
Akibatnya `{% for it in doc.items %}` → `TypeError: 'builtin_function_or_method' object is not iterable`.

Traceback asli (hasil reproduksi):
```
File "services/pdf_service.py", line 156, in render_document
    html = render_html(built["cfg"], built["branding"], built["doc"])
File "services/pdf_engine.py", line 180, in render_html
    return _tmpl.render(cfg=cfg, branding=branding, doc=doc)
File "<template>", line 76 (== file line 136), in top-level template code
TypeError: 'builtin_function_or_method' object is not iterable
```

### 1.3 FIX PASTI (sudah diverifikasi — 1 baris, 2 lokasi)
Ganti akses atribut `doc.items` → subscript `doc['items']` (subscript memakai getitem, ambil value key).

Di `pdf_engine.py`:
- `{% if doc.columns and doc.items %}`  →  `{% if doc.columns and doc['items'] %}`
- `{% for it in doc.items %}`           →  `{% for it in doc['items'] %}`

> Catatan: `it.get(c.key, '')` di baris yang sama TIDAK bermasalah (itu pemanggilan method,
> valid). `doc.columns`, `doc.totals`, `doc.meta`, dst. juga AMAN karena nama-nama itu bukan
> method milik `dict` (getattr gagal → Jinja fallback ke getitem). **Hanya `items` yang bentrok
> dengan `dict.items`.**

### 1.4 Bukti fix benar (hasil verifikasi in-memory, TANPA seed tambahan)
Setelah fix, render menghasilkan PDF valid (`magic=b'%PDF'`) untuk SEMUA doc_type yang ada datanya:
```
sales_order/so_007      : OK 19129 bytes %PDF
sales_order/so_001      : OK 18679 bytes %PDF
quotation/so_001        : OK 18558 bytes %PDF
purchase_order/po_001   : OK 17966 bytes %PDF
vendor_bill/vb_...      : OK 17425 bytes %PDF
ar_receipt/arc_...      : OK 17037 bytes %PDF
sales_return/sret_...   : OK 13056 bytes %PDF
purchase_return/pret_.. : OK 12298 bytes %PDF
makloon_spk/mko_...     : OK 11975 bytes %PDF
special_order/sord_...  : OK 18249 bytes %PDF
transfer                : (no seed data di warehouse_transfers)  <-- bukan bug
cycle_count             : (no seed data di cycle_count_sessions) <-- bukan bug
```
**Kesimpulan: ini SATU-SATUNYA bug. Tidak ada error lanjutan.**

### 1.5 Cara verifikasi setelah fix diterapkan
Reload otomatis (WatchFiles). Uji cepat via curl:
```bash
BASE=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"admin@kainnusantara.id","password":"demo12345"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -o /tmp/so.pdf -w "HTTP %{http_code} size=%{size_download}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/pdf/render/sales_order/so_007?format=pdf"
head -c4 /tmp/so.pdf   # harus: %PDF
```
Atau python langsung (paling cepat, tanpa auth):
```bash
cd /app/backend && python -c "
import asyncio; from services import pdf_service as svc
async def m():
    c,mt,b = await svc.render_document('sales_order','so_007',None,fmt='pdf',public_base='https://x')
    print(mt, len(c), c[:4])
asyncio.run(m())"
```

### 1.6 Setelah fix → WAJIB
- Tambah **seed data** untuk `warehouse_transfers` & `cycle_count_sessions` (atau uji dengan
  dokumen nyata yang dibuat lewat UI) supaya resolver `transfer` & `cycle_count` teruji.
- Jalankan **testing_agent_v3 (backend only)** untuk endpoint `/api/pdf/*` (render pdf+html,
  doc-types, RBAC, entity scoping / IDOR).

---

## 2. Arsitektur Platform PDF (yang sudah dibangun)

Stack: FastAPI + React + MongoDB. PDF native pakai **WeasyPrint** (deps C: pango/cairo sudah
terpasang global), template via **Jinja2**, QR via **qrcode**. Logo pakai **base64** (belum ada
object storage).

```
backend/
├── routers/pdf.py            # Endpoint /api/pdf/* (render, templates, branding, preview)
├── services/
│   ├── pdf_engine.py         # MASTER_TEMPLATE (Jinja2) + render_html() + render_pdf() fallback chain
│   ├── pdf_resolvers.py      # DOC_REGISTRY (SSOT doc_type) + resolver per dokumen → context ternormalisasi
│   └── pdf_service.py        # Orkestrasi: template cfg + branding + resolver + e-sign → HTML/PDF
├── permissions_config.py     # + permission: pdf_template, esign, document_delivery
scripts/
└── poc_document_platform.py  # POC Fase 1 (PASS) — referensi WeasyPrint/e-sign/WA simulator
frontend/src/utils/docPrint.js # Sistem PRINT HTML LAMA (Payment Voucher, PR, Tanda Terima) — dipertahankan
```

### 2.1 Endpoint yang tersedia (`routers/pdf.py`)
| Method | Path | Permission | Ket. |
|---|---|---|---|
| GET | `/api/pdf/doc-types` | `document:view` | daftar doc_type dari DOC_REGISTRY |
| GET | `/api/pdf/render/{doc_type}/{source_id}?format=pdf|html&entity_id=&download=` | `document:print` | **inti** — pdf=Response, html=HTMLResponse (buat preview iframe) |
| GET | `/api/pdf/templates/{doc_type}` | `pdf_template:view` | ambil config template + defaults |
| PUT | `/api/pdf/templates/{doc_type}` | `pdf_template:manage` | simpan config template global |
| GET | `/api/pdf/branding/{entity_id}` | `pdf_template:view` | kop/logo/TTD per entitas |
| PUT | `/api/pdf/branding/{entity_id}` | `pdf_template:manage` | simpan branding entitas |
| POST | `/api/pdf/preview` | `pdf_template:view` | preview HTML dgn cfg_override (buat designer) |

Router sudah **registered** di `server.py`. Entity scoping via `assert_entity_access` sudah dipasang di `/render`.

### 2.2 DOC_REGISTRY (SSOT jenis dokumen — `pdf_resolvers.py`)
Sudah ada 11 doc_type + resolver: `sales_order`, `quotation`, `purchase_order`, `vendor_bill`,
`ar_receipt`, `sales_return`, `purchase_return`, `makloon_spk`, `special_order`, `transfer`,
`cycle_count`. Setiap resolver: `async (doc, db) -> context dict` yang dikonsumsi `MASTER_TEMPLATE`.

Context standar yang dihasilkan resolver: `title, number, date, status, party_to{title,name,address,phone},
meta[], columns[], items[], totals[], terbilang, notes, signatures[], _amount`.

### 2.3 Config template & branding
- `DEFAULT_TEMPLATE_CFG` di `pdf_service.py`: paper, orientation, margin, font, warna, show_logo,
  show_terbilang, watermark, footer, title_override, custom_fields[], signature_slots[], hidden_fields[].
- Koleksi Mongo (dibuat on-demand via upsert): `pdf_templates` (config global per doc_type),
  `document_branding` (kop/logo/TTD per entity_id). **`pdf_template_overrides` per-entitas
  di plan BELUM diimplementasi** (saat ini branding per-entitas + template global).

---

## 3. Status per Fase (vs `/app/plan.md`)

| Fase | Judul | Status |
|---|---|---|
| 1 | POC Core (WeasyPrint/Jinja2/QR/e-sign/WA sim) | ✅ SELESAI (script PASS) |
| 2 | Backend PDF Engine + Template Store + Render Endpoints | ⚠️ SCAFFOLD SELESAI — **blocked oleh bug §1** (fix siap) |
| 3 | Advanced PDF Configuration UI (Template Designer + preview) | ⛔ BELUM |
| 4 | E‑Sign End-to-End + Verifikasi Publik | ⛔ BELUM |
| 5 | WhatsApp Integration (pluggable, default Meta, simulasi) | ⛔ BELUM |
| 6 | Implement SEMUA dokumen GAP + wiring tombol di FE | ⛔ BELUM |
| 7 | Final Gate + Docs + Comprehensive Testing | ⛔ BELUM |

---

## 4. Rencana Lanjutan (urutan kerja yang disarankan)

### Fase 2 (tutup dulu)
1. Terapkan fix §1.3. Verifikasi §1.5.
2. Seed `warehouse_transfers` & `cycle_count_sessions` (atau buat via UI) → uji 11/11 doc_type.
3. testing_agent_v3 (backend only) untuk `/api/pdf/*` (render, RBAC `document:print`, IDOR entitas).
4. Update `plan.md` Fase 2 → COMPLETED.

### Fase 3 — Advanced PDF Configuration UI (P0)
- Buat `frontend/src/features/pdf/PdfTemplateDesigner.jsx` (≤500 LoC/file; pecah jika perlu).
- Tabs editor: Layout / Kop / Font-Warna / Fields / Signatures / Footer-Watermark.
- Upload logo (base64) → simpan via `PUT /api/pdf/branding/{entity_id}`.
- Preview iframe (debounced) pakai `POST /api/pdf/preview` (kirim `config` sbg cfg_override) atau
  `GET /api/pdf/render/{doc_type}/{sample}?format=html`.
- Tombol "Download PDF" → `format=pdf`.
- Tambah nav: **Admin & Master Data → "PDF Templates"** (update `KN_13_NAVIGATION_MAP.md`).
- **WAJIB minta design_agent** dulu untuk guideline UI sebelum implementasi (ikuti design_guidelines.md).

### Fase 4 — E‑Sign (P1)
- Koleksi: `esign_requests`, `document_signatures` (hash, signer, base64 signature, verification_code, ip, timestamps).
- Endpoint: `POST /api/esign/request`, `POST /api/esign/verify`, `GET /api/esign/verify/{code}` (public).
- OTP channel pluggable `services/otp/` (default **simulasi via log** — sesuai keputusan user).
- Frontend: modal canvas signature + input OTP + halaman verifikasi publik standalone (route tanpa login).
- `pdf_service._attach_esign()` SUDAH SIAP menempel blok e-sign + QR bila ada `document_signatures`
  status `signed`. Tinggal isi datanya dari flow e-sign. `MASTER_TEMPLATE` sudah punya blok `.esign`.

### Fase 5 — WhatsApp (P1)
- **WAJIB panggil `integration_playbook_expert_v2`** untuk Meta WhatsApp Cloud API (media upload + template).
- `services/wa/base.py` + `meta_cloud.py` + registry; `integration_settings` (provider, simulate flag);
  koleksi `document_deliveries`.
- Endpoint `POST /api/deliveries/whatsapp/send`. Default **mode simulasi** (return `{status: simulated}`)
  sampai user memberi credential Meta. **Minta credential ke user sebelum implementasi live.**
- Frontend: tombol "Kirim WA" + drawer riwayat delivery; Admin settings + rule builder auto-send.

### Fase 6 — Wiring semua dokumen GAP
- Tambah tombol **Download PDF** + **Kirim WA** + (opsional) **E‑Sign** di detail view:
  OrderDetailPanel, PO detail, RFQ/Quotation, Vendor Bill, Kwitansi AR, Nota Retur (jual/beli),
  SPK Makloon, Special Order, Transfer/Surat Jalan, Stock Opname.
- Buat "Pusat Dokumen" (search/filter by doc_type/entity/date/status sign/delivery).
- Migrasi bertahap dok lama (surat jalan/invoice/tax invoice/GRN/PD/LPJ/Voucher/PR/Tanda Terima)
  ke engine baru — **tetap pertahankan endpoint/utils lama** (`docPrint.js`) sebagai fallback.

### Fase 7 — Final Gate + Testing
- testing_agent_v3 E2E (render→download→send→sign→verify), audit IDOR lintas entitas.
- Update `ENTITY_REGISTRY.md` (koleksi baru), `PRD.md`, `SESSION_LOG.md`, `KN_13_NAVIGATION_MAP.md`.
- Jalankan `scripts/gate.sh` sampai HIJAU 12/12.

---

## 5. Catatan Teknis & Gotchas Penting

- **WeasyPrint** deps C (pango/cairo) SUDAH terpasang global. Engine punya fallback chain:
  WeasyPrint → Playwright → reportlab (`pdf_engine.render_pdf`).
- **Font**: default `'DejaVu Sans'` (tersedia di WeasyPrint). Font dari daftar design guidelines
  hanya untuk UI web, bukan wajib untuk PDF.
- **Logo/TTD** disimpan **base64** (belum ada object storage). Jika butuh upload file skala besar,
  pertimbangkan minta object storage lewat integration agent.
- **E‑Sign OTP** & **WA** saat ini **SIMULASI** (keputusan user): OTP via log, WA return `simulated`.
  Jangan diubah ke live tanpa credential dari user.
- **RBAC false-negative (PENTING untuk testing)**: frontend testing agent kadang salah lapor RBAC
  "hilang dari Sidebar" saat viewport kecil meng-collapse HubTabs. Gunakan **Playwright/curl**
  sebagai ground-truth.
- **Jangan** ubah `frontend/.env:REACT_APP_BACKEND_URL` & `backend/.env:MONGO_URL`.
- **Jangan** pakai `npm` (pakai `yarn`). Jangan jalankan server manual (pakai `supervisorctl`).
- **UUID** untuk semua id (bukan ObjectId). Datetime pakai `timezone.utc`.
- Pola Jinja "gotcha": untuk dict, hindari `x.items`/`x.keys`/`x.values`/`x.get` sebagai **akses value**
  — pakai subscript `x['items']`. (Ini akar bug §1.)

---

## 6. Kredensial & Cara Testing

Login (seeded, idempotent) — detail lengkap di `/app/memory/test_credentials.md`:
| Role | Email | Password |
|---|---|---|
| admin | admin@kainnusantara.id | demo12345 |
| sales | sales@kainnusantara.id | demo12345 |
| manager | manager@kainnusantara.id | demo12345 |
| warehouse | warehouse@kainnusantara.id | demo12345 |

- Auth: `POST /api/auth/login` → `token` → header `Authorization: Bearer <token>` atau `X-Session-Token`.
- Entities: `ent_ksc` (PT Kain Suka Cita, PKP), `ent_kanda` (CV Kanda Suka, non-PKP).
- Base URL: `REACT_APP_BACKEND_URL` + `/api`.

### Perintah cheat-sheet
```bash
supervisorctl status
tail -n 80 /var/log/supervisor/backend.*.log
supervisorctl restart backend frontend          # hanya setelah ubah deps/.env
cd /app/backend && esbuild ../frontend/src --loader:.js=jsx --bundle --outfile=/dev/null  # cek FE compile
```

---

## 7. File Referensi (baca ini saat mulai)
- `/app/plan.md` — 7-Fase Document Platform (SSOT rencana)
- `/app/backend/services/pdf_engine.py` — **lokasi bug §1**
- `/app/backend/services/pdf_resolvers.py` — DOC_REGISTRY + resolver
- `/app/backend/services/pdf_service.py` — orkestrasi + e-sign attach + branding
- `/app/backend/routers/pdf.py` — endpoint
- `/app/backend/permissions_config.py` — permission `pdf_template/esign/document_delivery`
- `/app/scripts/poc_document_platform.py` — referensi POC (PASS)
- `/app/frontend/src/utils/docPrint.js` — sistem print HTML lama (dipertahankan)
- `/app/memory/test_credentials.md`, `/app/memory/PRD.md`, `/app/memory/SESSION_LOG.md`
