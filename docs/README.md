# Kain Nusantara — Dokumentasi

Folder ini berisi dokumentasi sistem **Kain Nusantara ERP/WMS**.

## Daftar Dokumen

| File | Deskripsi |
|---|---|
| [`SYSTEM_ANALYSIS.md`](./SYSTEM_ANALYSIS.md) | **Analisis komprehensif** seluruh modul, gap, potential improvement, dan roadmap modul baru untuk menjadi end-to-end ERP. |

## Quick Links

### Seed Data
Untuk reset data ke kondisi realistis (semua tour bisa berjalan):

**Opsi 1 — Dari UI (Admin only, RECOMMENDED untuk production)**
1. Login sebagai `admin`
2. Buka menu **Admin** di sidebar
3. Klik tombol **"Reset Demo Data"** (oranye) di pojok kanan header
4. Konfirmasi dialog → tunggu 5–10 detik
5. Data demo akan ter-load (notice di pojok atas menampilkan summary)

**Opsi 2 — Dari CLI (preview/dev only)**
```bash
cd /app
python seed_realistic.py
```

**Opsi 3 — Via API langsung (untuk automation)**
```bash
# 1. Login dapat token
TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@kainnusantara.id","password":"demo12345"}' \
  | jq -r .token)

# 2. Trigger seed
curl -X POST "$BASE_URL/api/admin/seed-demo" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"YES_CLEAR_AND_SEED_DEMO_DATA"}'
```

**Safety:**
- Endpoint hanya bisa diakses oleh user role **admin** (permission check `permission:update`).
- Wajib kirim `confirm` token persis `"YES_CLEAR_AND_SEED_DEMO_DATA"`.
- Bisa dinonaktifkan dengan env var `SEED_DEMO_ENABLED=false` di production setelah data real masuk.

Script ini akan:
- Clear semua koleksi operasional
- Insert 5 user (admin, sales, manager, warehouse×2)
- Insert 7 produk kain (Batik, Tenun, Lurik, Songket, Ulos, Jumputan, Endek)
- Insert 5 customer + 3 warehouse (Jakarta/Bandung/Surabaya)
- Insert 6 Purchase Order (status mix: completed, receiving, created)
- Insert 8 Sales Order (status mix: dispatched, picking, approved, waiting_approval, reserved)
- Insert inventory balances, movements, audit logs, document templates, permissions

### Demo Account

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `demo12345` |
| Sales | `sales` | `demo12345` |
| Manager | `manager` | `demo12345` |
| Warehouse | `warehouse` | `demo12345` |
| Warehouse #2 | `warehouse2` | `demo12345` |

### Smart Guidelines (Onboarding Tour)

Setelah login, klik tombol **"Help & Tours"** di pojok kanan-bawah untuk mengakses tutorial interaktif. Tour yang ditampilkan disesuaikan dengan role login.

| Role | Tour Tersedia |
|---|---|
| Admin | Semua 7 tour |
| Sales | Create Sales Order, Order Dashboard |
| Manager | Approve Order, Inventory, Order Dashboard |
| Warehouse | Process Inbound, Process Outbound, Inventory |

---

## Arsitektur Singkat

```
[ Browser ]
    ↓
[ React 19 + TailwindCSS + Shadcn/UI ]
    ↓ (REST /api/*)
[ FastAPI + Pydantic ]
    ↓
[ MongoDB ]
```

- **Frontend**: `/app/frontend/src/`
- **Backend**: `/app/backend/`
- **Routers**: 24 modular endpoints (`/app/backend/routers/`)
- **Services**: business logic (`/app/backend/services/`)
- **Schemas**: Pydantic models (`/app/backend/schemas.py`)
- **DB**: MongoDB dengan UUID ID + timezone-aware timestamps
