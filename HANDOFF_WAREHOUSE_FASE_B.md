# HANDOFF — Warehouse Fase B (Location/Putaway B1 + Reorder/ROP B2)

> Dokumen ini dibuat untuk melanjutkan pekerjaan di agent berikutnya.
> Bahasa komunikasi user: **Bahasa Indonesia**. Balas SELALU dalam Bahasa Indonesia.
> Tanggal handoff: session warehouse Fase B (IN PROGRESS).

---

## 1) RINGKASAN STATUS

> ✅ **UPDATE (Session #072): FASE B SELESAI & GREEN.** `LocationPutawayView` sudah di-wire ke `App.js`, 3 bug fix (WarehouseStructure schema crash, setField edit crash, permission warehouse/manager) terverifikasi. testing_agent_v3 iter_103 = BE 100% (9/9), FE 100%. Guardrails LULUS. plan.md ditandai Fase B COMPLETED.

| Bagian | Status | Catatan |
|---|---|---|
| Backend Fase B1 (Location & Putaway) | ✅ SELESAI & JALAN | health `GET /api/` → 200 |
| Backend Fase B2 (Reorder/ROP velocity) | ✅ SELESAI | endpoint reorder-suggestions ter-enhance |
| Frontend `LocationPutawayView.jsx` | ✅ WIRED & TESTED | di-render pada `activeView === "wms-locations"` |
| Navigasi `navigationConfig.js` | ✅ SELESAI | nav id = **`wms-locations`** |
| E2E Testing (testing_agent_v3) | ✅ HIJAU | iter_103: BE 100% (9/9), FE 100%, 3/3 regression fix |
| Stock Analytics (Fase 5, sesi sebelumnya) | ✅ SELESAI & WIRED | render di `App.js` (`cs-stock-analytics`) |
| SSOT Hardening (Fase A) | ✅ SELESAI | transfers/cycle_count/wms roll-based |

---

## 2) SATU-SATUNYA HAL YANG KURANG (KERJAKAN PERTAMA)

`App.js` **belum meng-import dan me-render** `LocationPutawayView`.
Karena itu, klik menu "Lokasi & Putaway" tidak menampilkan komponen apa pun.

### KOREKSI PENTING dari analisis lama
Analisis sebelumnya menyebut `activeView === "locations"`. **ITU SALAH.**
Nav id yang benar (sesuai `navigationConfig.js`) adalah **`wms-locations`**.
`wms-locations` TIDAK diawali `cs-`, jadi TIDAK perlu ditambahkan ke `LIVE_CS_VIEWS`
dan tidak akan diblok oleh guard ComingSoon.

### Props yang dibutuhkan komponen
```jsx
// frontend/src/features/wms/LocationPutawayView.jsx (baris 48)
export default function LocationPutawayView({ currentUser, selectedEntity }) { ... }
```

### LANGKAH FIX (2 edit di `frontend/src/App.js`)

**Edit 1 — Tambahkan import** (dekat baris 78, setelah import StockAnalyticsView):
```jsx
import StockAnalyticsView from "./features/inventory/StockAnalyticsView";
import LocationPutawayView from "./features/wms/LocationPutawayView";   // <-- TAMBAHKAN
```

**Edit 2 — Tambahkan render block** (dekat baris 420, di samping cs-stock-analytics):
```jsx
{activeView === "cs-stock-analytics" && <StockAnalyticsView currentUser={user} selectedEntity={selectedEntity} />}
{activeView === "wms-locations" && <LocationPutawayView currentUser={user} selectedEntity={selectedEntity} />}   // <-- TAMBAHKAN
```

> Catatan: variabel user di App.js bernama `user` (bukan `currentUser`) dan `selectedEntity`.
> Ikuti pola persis seperti `StockAnalyticsView` yang sudah bekerja.

---

## 3) SETELAH WIRING — VERIFIKASI

1. **Cek kompilasi frontend** (JANGAN pakai npm; pakai esbuild):
   ```bash
   cd /app/frontend && npx esbuild src/ --loader:.js=jsx --bundle --outfile=/dev/null
   ```
2. **Screenshot** menu "Lokasi & Putaway" via preview URL untuk verifikasi visual.
3. **Login test**: `warehouse@kainnusantara.id` / `demo12345` (menu ini role: admin, warehouse, manager).

---

## 4) E2E TESTING (WAJIB — via testing_agent_v3, tipe: both)

Uji skenario berikut:
- **Location CRUD**: `GET /api/warehouses/{id}/locations` — buat/edit/hapus struktur Zone→Rack→Level→Bin, simpan.
- **Putaway**: `GET /api/inventory/putaway/queue` (antrean roll belum ditempatkan), `POST /api/inventory/putaway` (roll_id, bin_id) → roll pindah ke bin.
- **Reorder/ROP**: `GET /api/purchase-requisitions/reorder-suggestions` — validasi saran berbasis velocity (fast/slow) & ROP.
- **Regresi SSOT**: pastikan putaway tetap ROLL-BASED, tidak ada `$inc` langsung ke `inventory_balances`.
- **Frontend**: render view, util-bar kapasitas bin, aksi putaway dari UI.

Setelah testing: baca `/app/test_reports/iteration_{n}.json`, perbaiki semua bug (high→low), lalu update `plan.md`.

---

## 5) FILE-FILE KUNCI (TERVERIFIKASI ADA)

### Backend (SELESAI)
- `backend/services/location_service.py` — 167 baris, **untracked/baru**. Fungsi: `putaway_queue()`, `putaway_roll()`.
- `backend/routers/inventory.py` — endpoint putaway queue/action + stock-analytics.
- `backend/routers/warehouses.py` — `GET /api/warehouses/{warehouse_id}/locations`.
- `backend/routers/purchase_requisitions.py` — `GET /api/purchase-requisitions/reorder-suggestions`.
- `backend/services/purchase_requisition_service.py` — enhancement velocity/ROP (+109/-46 baris).
- `backend/services/config_service.py` — threshold config baru (+6 baris).
- `backend/services/stock_analytics_service.py` — enhancement (+31 baris).

### Frontend
- `frontend/src/features/wms/LocationPutawayView.jsx` — 340 baris, **untracked/baru**, export default `{ currentUser, selectedEntity }`. ⚠️ perlu di-wire.
- `frontend/src/config/navigationConfig.js` — nav `wms-locations` (label "Lokasi & Putaway", icon MapPin, roles admin/warehouse/manager) + `cs-stock-analytics`.
- `frontend/src/App.js` — **PERLU DIEDIT** (import + render block, lihat Bagian 2).
- `frontend/src/features/inventory/StockAnalyticsView.jsx` — referensi pola wiring yang sudah benar.

### Git status saat handoff (belum di-commit)
```
 M backend/routers/inventory.py
 M backend/routers/purchase_requisitions.py
 M backend/routers/warehouses.py
 M backend/services/config_service.py
 M backend/services/purchase_requisition_service.py
 M backend/services/stock_analytics_service.py
 M frontend/src/config/navigationConfig.js
?? backend/services/location_service.py
?? frontend/src/features/wms/LocationPutawayView.jsx
```

---

## 6) MANDAT ARSITEKTUR (JANGAN DILANGGAR)

- **Roll-as-SSOT**: SELALU ubah inventory via `inventory_rolls`. JANGAN `$inc` langsung ke `inventory_balances` (itu proyeksi turunan).
- **Multi-entity**: banyak request inventory butuh header `X-Entity-Id`.
- **JANGAN overwrite `.env`**: `MONGO_URL` (backend) & `REACT_APP_BACKEND_URL` (frontend) harus tetap.
- **JANGAN pakai npm** — pakai `yarn`. Jangan jalankan server manual — pakai `supervisorctl`.
- Semua route backend diawali `/api`. Gunakan UUID (bukan ObjectId), datetime pakai `timezone.utc`.

### Skema DB terkait
- `inventory_rolls` (SSOT): `{ product_sku, warehouse_id, owner_entity_id, status, bin_id }`
- `inventory_balances` (proyeksi turunan): `{ product_sku, warehouse_id, owner_entity_id, available_qty }`
- `warehouse_locations` (baru): `{ warehouse_id, zones[] → racks[] → levels[] → bins[] }`

---

## 7) KREDENSIAL TEST

- Password semua user: `demo12345`
- Users: `admin@kainnusantara.id`, `sales@kainnusantara.id`, `manager@kainnusantara.id`, `warehouse@kainnusantara.id`
- Preview URL: https://epic-cannon-6.preview.emergentagent.com

---

## 8) TASK BERIKUTNYA (SETELAH FASE B FIX + TEST HIJAU)

Prioritas (belum dikonfirmasi user — TANYA dulu):
1. **P1**: RFID Simulator (Fase 5 — 4 menu `cs-rfid-*` masih placeholder).
2. **P2**: SMTP PO PDF (email Purchase Order PDF) — tercatat NEXT di plan.md.
3. **P3**: Budget/Commitment Control.
4. **P4**: Multi-currency / FX.

Tech-debt / future:
- Refactor `backend/routers/sales_orders.py` & `frontend/src/features/sales/CheckoutDrawer.jsx` (keduanya melebihi batas baris / gagal compliance).
- Bug UX: `features/finance/BiFinanceView.jsx` belum ada empty-state guard untuk tabel & chart (di-flag `ux_audit.py`).
- BOM Printing (`cs-bom` Fase 3), Price List per Customer UI wiring.

---

## 9) TODO RINGKAS UNTUK AGENT BERIKUTNYA

- [ ] Edit `App.js`: import `LocationPutawayView` (~baris 78).
- [ ] Edit `App.js`: render block `activeView === "wms-locations"` (~baris 420).
- [ ] `npx esbuild src/ --loader:.js=jsx --bundle --outfile=/dev/null` → pastikan tanpa error.
- [ ] Screenshot menu "Lokasi & Putaway" (login warehouse) → verifikasi visual.
- [ ] Jalankan `testing_agent_v3` (both) untuk Location CRUD + Putaway + Reorder/ROP.
- [ ] Baca test report, fix semua bug, cek regresi SSOT.
- [ ] Update `plan.md` → tandai Fase B COMPLETED.
- [ ] Tanya user prioritas task berikutnya (Bagian 8).
