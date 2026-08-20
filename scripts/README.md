# KN3 GUARDRAILS — Executable Gate Suite

Kumpulan **guardrail yang bisa GAGAL** (exit ≠ 0) untuk mencegah bug data,
drift, 5xx, dan utang UX pada development Kain Nusantara. Diadaptasi dari
kerangka `torado60` + divalidasi terhadap kontrak NYATA KN3.

> Baca dulu: `/app/memory/ENGINEERING_GUARDRAILS.md` (RC-1..RC-15) &
> `/app/docs/UX_USABILITY_STANDARD.md`.

## Urutan pemakaian (sebelum `finish`)

```bash
cd /app
bash scripts/seed_reset.sh              # 1) seed BERSIH + [GATE] contract + integrity
python scripts/health_check.py          # 2) endpoint kritis (cek ISI, bukan 200)
python scripts/audit_endpoint_sweep.py  # 3) sweep SEMUA GET /api → cari 5xx
python scripts/ux_audit.py              # 4) baseline UX
```

## Daftar script

| Script | Fungsi | Exit≠0 saat |
|--------|--------|-------------|
| `seed_reset.sh` | Reset DB ke data realistis bersih lalu jalankan [GATE] (contract + api_contract + integrity) | seed/gagal gate |
| `verify_data_integrity.py` ⭐ | L0 self-check vs ENTITY_REGISTRY · L1/L2 drift · L4 invarian (stok, order) · L5 number-series · L3 intent lintas-endpoint | invarian dilanggar |
| `verify_api_contract.py` ⭐ | **(NEW)** Check A duplicate route · Check B FE call→route exist · Check C FE field ⊆ BE response | drift FE↔BE |
| `verify_contract.py` | Statik: nama koleksi kanonik vs TERLARANG; deteksi `db.x` **dan** `db["x"]` | ada koleksi terlarang |
| `health_check.py` | Login + sweep endpoint kritis, cek jumlah item | ada FAIL/5xx |
| `audit_endpoint_sweep.py` | Hit SEMUA GET /api (resolve path param) | ada 5xx/exception |
| `ux_audit.py` | Baseline UX (loading/empty/chart/`tabular-nums`/testid) | `--strict` & ada ERROR |
| `audit_collection_drift.py` | Koleksi dibaca di kode tapi kosong/hilang di DB | (laporan) |
| `find_dead_services.py` | Modul service tak terpakai | (laporan) |
| `validate_compliance.py` | (eksisting) file-size & naming convention | pelanggaran |
| `check_nav_map.py` | (eksisting) navigasi vs KN_13 | pelanggaran |
| `ui_smoke.py` | **Smoke UI POS end-to-end (browser, TOLERAN)** — login → navigasi semua menu → POS → quickview → checkout step-1. | (laporan, selalu exit 0) |

## UI Smoke (Playwright) — `ui_smoke.py`

Sanity-check UI cepat tanpa jebakan timeout. **Jalankan:**

```bash
/opt/plugins-venv/bin/python scripts/ui_smoke.py            # default http://localhost:3000
/opt/plugins-venv/bin/python scripts/ui_smoke.py --url <preview-url> --role sales
```

**PELAJARAN (kenapa testing agent dulu timeout) — WAJIB dipakai juga oleh testing agent:**

1. **JANGAN** `goto(wait_until="networkidle")` → WebSocket HMR dev-server tak
   pernah idle → hang/timeout. Pakai `domcontentloaded` + `wait_for_selector`.
2. Login **bukan** `input[type=email]`. Pakai `data-testid`:
   `login-email-input`, `login-password-input`, `login-submit-button`,
   atau 1-klik `demo-login-admin-button` (juga -sales/-manager/-warehouse). Password semua = `demo12345`.
3. Sidebar item = `nav-<id>`, grup = `nav-group-toggle-<groupId>`; highlight aktif = class `active`.
4. POS = `nav-sales`; kartu 1 tombol `add-to-cart-button-<id>` → popup
   `product-quickview` → `quickview-add-button` → `floating-cart-button` →
   `checkout-step-1` (ringkasan `checkout-step1-items`).
5. Abaikan console-error dev-only (HMR `ws://localhost:443`, sockjs, ResizeObserver).

Smoke ini **toleran** (selalu exit 0). Kalau gagal/timeout di otomasi → tidak apa-apa, verifikasi manual / lanjutkan.


## Aturan emas

1. Verifikasi di **DB bersih** (seed_reset) — DB dev kotor menutupi drift.
2. "200 / running" **bukan** bukti benar — cek **nilai** & **invarian**.
3. Tambah fitur ⇒ tambah Concept/endpoint/koleksi ke gate terkait (lihat
   ENGINEERING_GUARDRAILS.md §7). Guardrail yang tak tumbuh akan membusuk.
4. Jangan klaim hijau palsu (RC-10). FAIL yang disengaja = catat sebagai
   keputusan owner, jangan disembunyikan.

## Variabel lingkungan

- `MONGO_URL`, `DB_NAME` → dari `backend/.env` (auto via `load_dotenv`).
- `API_BASE` (default `http://localhost:8001`), `KN_ADMIN_EMAIL`, `KN_ADMIN_PASS`
  bisa di-override untuk lingkungan lain.
