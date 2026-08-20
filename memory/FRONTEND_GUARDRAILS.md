# FRONTEND GUARDRAILS — KN7 (React)
**Status:** WAJIB dipatuhi. Sejajar dengan `ENGINEERING_GUARDRAILS.md` (backend).
**Prinsip emas:** **KODE MENANG atas DOKUMEN.** Ikuti konvensi nyata yang berjalan di
`/app/frontend/src`, bukan standar aspiratif (Zustand/TanStack/ECharts TIDAK dipakai).

> Cara cek cepat tanpa baca semua dokumen: `bash scripts/load_context.sh`
> lalu jalankan gate FE: `esbuild`, `ux_audit.py`, `verify_api_contract.py`, `check_nav_map.py`.

---

## 0. ARSITEKTUR FE NYATA (jangan diubah tanpa alasan)
```
src/
  App.js                      ← root: state global (user, token, cart, view) + routing view (default export)
  index.js / index.css
  components/                 ← komponen SHARED (CartPanel, CustomerPanel, ProductCard, CoreWidgets, LoginScreen)
  components/ui/              ← shadcn (Button, Select, Dialog, ...) — PAKAI INI
  features/<domain>/          ← halaman per domain (sales, orders, wms, admin, transfers, ...)
  hooks/useAppActions.js      ← aksi data SHARED (login, addToCart, submitOrder, mutateOrder, ...)
  services/apiClient.js       ← axios instance + `API` const + setAuthToken
  config/navigationConfig.js  ← menu, PAGE_META, ROLE_MENU_ALLOWLIST
  utils/formatters.js         ← formatCurrency, formatQty, cn
  styles/ tokens.css·components.css·layout.css·login.css  + App.css
```
- Stack nyata: **React + axios + Recharts + Tailwind + shadcn + lucide-react**. Tidak ada Redux/Zustand/TanStack/ECharts.

---

## 1. KONTRAK API DI FRONTEND (WAJIB)
1. **Semua call lewat `services/apiClient.js`** → `import axios, { API } from ".../services/apiClient"`.
   - `API = ${REACT_APP_BACKEND_URL}/api`. **JANGAN** hardcode URL/host. **JANGAN** `fetch()` mentah.
2. **Respons BE = ARRAY/OBJEK telanjang** (TANPA envelope `{success,data}`). Selalu guard:
   `const rows = Array.isArray(res.data) ? res.data : []`. Jangan asумsikan `res.data.data`.
3. **Auth**: token field bernama **`token`** (prefix `sess_`), dipasang global via `setAuthToken` →
   header `Authorization: Bearer sess_...`. Jangan simpan rahasia/API key di FE.
4. **Path endpoint harus literal** untuk lolos `verify_api_contract` CHECK B.
   ✅ `axios.post(\`${API}/price-approvals/${id}/approve\`)`  ← segmen akhir literal
   ❌ `axios.post(\`${API}/price-approvals/${id}/${action}\`)` ← `${action}` tak bisa di-resolve gate.
5. Aksi lintas-halaman → taruh di `hooks/useAppActions.js`. Halaman boleh axios langsung untuk domainnya
   sendiri (pola `InterCompanyTransfers.jsx`, `PriceApprovals.jsx`), tetap pakai `API` + path literal.

---

## 2. UI / UX (WAJIB — ditegakkan `ux_audit.py`, target 0 ERROR)
- **Komponen shadcn** dari `@/components/ui` (atau `components/ui`). **`<select>` bawaan peramban DILARANG** (ERROR E4 sejak FASE P6) →
  pakai `Select`. Hindari `<button>`/`<input>` telanjang bila ada padanan shadcn.
- **Ikon HANYA `lucide-react`.** Tanpa emoji sebagai ikon UI.
- **Uang & qty**: kelas `tabular-nums` + `formatCurrency`/`formatQty` (jangan format manual). (WARN W1)
- **Chart Recharts** wajib ada `<Tooltip>`. (WARN W4)
- **State data wajib**: setiap view yang fetch HARUS punya **loading** (skeleton/teks), **empty state**
  (pesan + aksi), dan **error state** (pesan + retry). Tanpa ketiganya = pelanggaran.
- **Warna**: pakai token/palet eksisting (navy `#0058CC`, ungu aksen `#6B219A`, status-pill di
  `styles/components.css`). DILARANG merah/hijau/biru mentah (`#FF0000` dsb) & gradien berlebihan.
- **Status pill**: pakai kelas `status-<status>` yang sudah ada; tambah kelas baru di `components.css`
  bila status baru (jangan inline warna acak).
- **Responsif** + kontras AA + elemen interaktif punya state hover/focus/disabled.

---

## 3. TESTABILITY (WAJIB)
- **`data-testid` di SETIAP** elemen interaktif (button/input/link/select/dialog) **dan** elemen yang
  menampilkan info kritis (saldo, total, status, pesan error).
- Penamaan **kebab-case berbasis peran**, unik: `price-approvals-approve-${id}`, `cart-item-special-${id}`.
- Jangan duplikat / jangan hapus testid yang sudah dipakai test.

---

## 4. NAVIGASI (config-driven)
- Tambah menu HANYA via `config/navigationConfig.js`: `PAGE_META`, array `items`, `ROLE_MENU_ALLOWLIST`
  (admin lihat semua; sales/manager/warehouse sesuai allowlist) → lalu render di `App.js`.
- Ikuti **Navigation Map (KN_13)**. ⚠️ Backlog NAV-01: konvensi `data-testid` nav (`nav-*`, `wms-tab-*`)
  belum sesuai KN_13 — saat menyentuh nav, selaraskan.
- Jangan tambah view di luar Navigation Map tanpa STOP & ASK.

---

## 5. EXPORT, UKURAN FILE, ENV
- **Komponen** → named export (`export function X`/`export const X`); **Halaman/Page** → default export.
- **Batas baris**: `.jsx` ≤ **500**, file `.js` (hooks/services/utils/config) ≤ **300**, `.css` ≤ **400**.
  Lewat batas = WAJIB refactor (dipecah). (Ditegakkan `validate_compliance.py`.)
- **ENV**: hanya `REACT_APP_BACKEND_URL` (+ `/api`). Jangan ubah `.env`. Jangan hardcode URL/secret.
- **Paket**: pakai **`yarn add`** — JANGAN `npm`.

---

## 6. ROOT CAUSE TAXONOMY (FE) — kenali & hindari
| Kode | Gejala | Akar | Cegah |
|------|--------|------|-------|
| RC-F1 | Layar putih | import komponen/ikon hilang | cek import; `esbuild` |
| RC-F2 | `.map is not a function` | asumsi array padahal undefined/objek | `Array.isArray()` guard |
| RC-F3 | 401/403 beruntun | token tak ter-set / role tak punya izin | `setAuthToken`; cek allowlist + permission |
| RC-F4 | FE↔BE drift | path/field FE ≠ route/respons BE | `verify_api_contract.py`; path literal |
| RC-F5 | `body stream already read` | double-fetch StrictMode | async IIFE + cleanup di useEffect |
| RC-F6 | URL salah di prod | hardcode host | selalu `${API}` dari env |
| RC-F7 | Test rapuh | testid hilang/duplikat | testid unik wajib |
| RC-F8 | UI "datar"/jelek | abaikan token warna & state data | ikuti §2; loading/empty/error |

---

## 7. ALUR KERJA WAJIB SEBELUM "DONE" (FE)
1. `npx esbuild src/index.js --loader:.js=jsx --bundle --outfile=/dev/null` → 0 error.
2. `python scripts/ux_audit.py` → 0 ERROR (WARN dicatat ke backlog).
3. `python scripts/verify_api_contract.py` → FE↔BE OK.
4. `python scripts/check_nav_map.py` bila menyentuh navigasi.
5. `python scripts/validate_compliance.py` → 0 FAIL (termasuk batas ukuran file).
6. Screenshot via preview URL + login pakai `data-testid` (`login-email-input`/`login-password-input`/`login-submit-button`).
   Catatan: input email **bukan** `type=email` (default text) → selektor pakai testid.
7. Verifikasi visual: loading/empty/error tampil, angka rapi (`tabular-nums`), tidak ada console error.

---

## 8. CHECKLIST RINGKAS (tempel di PR/laporan)
- [ ] Semua call via `apiClient` + `API`, path literal, guard `Array.isArray`.
- [ ] shadcn (bukan native), ikon lucide, `tabular-nums`, chart ada Tooltip.
- [ ] loading + empty + error state untuk setiap view data.
- [ ] `data-testid` lengkap & unik (interaktif + info kritis).
- [ ] menu via navigationConfig + ROLE_MENU_ALLOWLIST + render App.js.
- [ ] export benar (komponen named / page default); ukuran file dalam batas.
- [ ] tidak hardcode URL/secret; pakai env; yarn (bukan npm).
- [ ] esbuild + ux_audit(0 ERROR) + verify_api_contract OK + validate_compliance(0 FAIL).
