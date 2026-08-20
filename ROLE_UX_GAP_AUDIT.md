# ROLE/UX GAP AUDIT — Pembeda Pengalaman Sales vs Admin (KN3)

> Audit lanjutan diminta user: "system masih belum bisa membedakan dengan jelas [Sales vs Admin]…
> secara fungsionalitas iya, namun dari segi pengalaman pengguna belum."
> Metode: pembacaan langsung `navigationConfig.js`, `App.js`, `permissions_config.py`, +
> login nyata sebagai Sales & Admin (screenshot). Semua temuan grounded.

---

## 1. MODEL PEMBEDA PERAN SAAT INI (FAKTA)

Pembedaan peran HANYA terjadi di 2 lapis, dan dangkal:
1. **Filter navigasi** (`buildNavGroups(role)`) — menyembunyikan item sidebar per `roles[]`.
2. **Gate `isManager`** ad-hoc di beberapa komponen (mis. CRM menyembunyikan tab "Skema & Target").
3. **Permission matrix** (`DEFAULT_PERMISSIONS`) — kontrol API per modul/aksi.

**Yang TIDAK ada:** landing/home per peran, framing informasi per peran, chrome (header KPI) per peran, workspace personal sales. Maka secara **pengalaman**, ketiga peran terasa seperti aplikasi yang sama dengan menu dimatikan sebagian.

---

## 2. APA YANG DIALAMI TIAP PERAN (HASIL LOGIN NYATA)

### 2.1 SALES (Ayu Permatasari) — bukti screenshot
- **Landing = POS** ("Katalog POS & Reservasi"). `defaultViewForRole('sales') = 'sales'`.
- **Header atas = KPI GLOBAL** (Produk Aktif 7, Available 3.054, Reserved 221, Active Orders 7, Gudang 3) + checklist onboarding — **sama persis** dengan admin. Ini **bukan angka personal sales**, bahkan menampilkan "Gudang / Buka WMS".
- **Sidebar Sales menampilkan item BACK-OFFICE Pembelian:**
  - **Landed Cost (HPP)** ⚠️ — data **biaya pokok/margin** (sangat sensitif untuk sales).
  - **Tagihan Supplier** (Vendor Bills) — irelevan untuk sales.
  - **Faktur Pajak Masukan** (Input VAT) — tugas finance.
  - **Purchase Requisition**, **Pesanan Pembelian (view)**.
- **Tidak ada** halaman "Performa Saya" (komisi, target, pencapaian, customer saya, penagihan saya).

### 2.2 ADMIN (Budi Santoso) — bukti screenshot
- **Landing = "Master Data & Audit"** — layar **CRUD** (daftar Product + Edit/Deactivate).
- **Header atas = KPI global + onboarding** identik dengan sales.
- Sidebar = semua grup (Penjualan, Pembelian, Gudang, RFID, Keuangan, SDM, Analitik, Dokumen, Admin).
- **Tidak ada executive overview** (kesehatan bisnis sekilas): admin harus menggali ke modul.

### 2.3 Permission server-side (FAKTA)
- Sales `view` pada: **`landed_cost`, `vendor_bill`, `input_tax`, `purchase_order`** → **biaya/HPP & back-office terbuka untuk sales di level API**, bukan hanya nav.
- Sales `create/print` **`tax_invoice`** (Faktur Pajak Jual) & `delete` **`price_approval`** → scope berlebih untuk peran sales.

---

## 3. TEMUAN GAP (RANKED BY SEVERITY)

| # | Severity | Temuan | Bukti | Dampak |
|---|---|---|---|---|
| G1 | 🔴 TINGGI | **Tidak ada Sales personal workspace.** Sales dilempar ke POS, tanpa "performa saya". | `defaultViewForRole`, screenshot | Sales tak punya rasa "ini ruang kerja saya"; insentif/target/penagihan tak terlihat harian. |
| G2 | 🔴 TINGGI | **Back-office & biaya (HPP) terekspos ke Sales** (nav + permission: landed_cost/vendor_bill/input_tax/PO). | navConfig + DEFAULT_PERMISSIONS | Kebocoran margin/biaya; clutter; makin krusial karena insentif baru = **margin-aware** (cost makin sensitif). |
| G3 | 🟠 SEDANG | **Chrome identik lintas peran** (KPI strip global + onboarding sama untuk semua). | screenshot sales vs admin | Sales melihat metrik gudang/global, bukan miliknya → tidak relevan, membingungkan. |
| G4 | 🟠 SEDANG | **Admin tanpa executive overview** (landing = CRUD master data). | screenshot admin | Pengambilan keputusan lambat; tak ada "control tower". |
| G5 | 🟠 SEDANG | **Scope sales berlebih**: bisa terbitkan Faktur Pajak Jual, hapus price approval. | DEFAULT_PERMISSIONS | Tanggung jawab finance bocor ke sales; risiko kontrol. |
| G6 | 🟢 RENDAH | **Filter boros space** (`.field width:100%` menimpa `w-[150px]`). | components.css + screenshot | Estetika/efisiensi layar (keluhan user). |
| G7 | 🟢 RENDAH | **"Beranda" menyesatkan** — bukan home, hanya redirect ke alat utama peran. | navConfig | Konsep "rumah" hilang. |
| G8 | 🟢 RENDAH | **Tanpa progressive disclosure** — tabel padat sama untuk semua peran. | umum | Beban kognitif, terutama sales lapangan. |

### Yang SUDAH benar (pola untuk ditiru)
- **CRM**: tab "Skema & Target" & "Approval Kredit" disembunyikan untuk sales; daftar customer "Milik Saya" vs "(Semua)". Ini **pola pembeda peran yang baik** — tapi jadi pengecualian, bukan norma.

---

## 4. REKOMENDASI (ROLE-TAILORED IA)

### R1 — Home per peran (HIGH)
- **Sales Home** (default sales): "Performa Saya" → komisi MTD (model per-SKU baru: akrual & proyeksi), target & pencapaian, customer saya + status kredit, penagihan saya (worklist), order terbaru, quick-action **Buat Order**. (Tanpa biaya/HPP.)
- **Admin Home**: control tower → penjualan hari ini/MTD, AR aging, approval tertunda, low-stock/reorder, ringkasan payout insentif, switch entitas. (Bisa tab "Ringkasan" di samping Master Data.)
- **Manager Home**: performa tim (leaderboard, target tim, koleksi, approval).

### R2 — Rapikan akses Sales (HIGH, configurable)
- Hapus dari nav & permission sales: **landed_cost, vendor_bill, input_tax, purchase_order(view)**. Pertahankan **stok read** (untuk cek ketersediaan).
- Re-scope **tax_invoice** (terbit) & **price_approval delete** → manager/admin (atau toggle di matrix).
- Lakukan **lewat permission matrix** (admin bisa atur), bukan hardcode → tetap fleksibel.

### R3 — Chrome sadar-peran (MEDIUM)
- KPI strip dipersonalisasi: sales = angka miliknya; admin = perusahaan; warehouse = operasional. Sembunyikan onboarding setelah selesai.

### R4 — UI polish (LOW, cepat)
- Perbaiki sizing filter (bar kompak / popover "Filter"), densitas konsisten, progressive disclosure.

### R5 — Governance (MEDIUM)
- Jadikan semua pembeda peran **berbasis konfigurasi** (permission matrix + setting "home per role") agar tidak getas.

---

## 5. KETERKAITAN DENGAN REDESAIN INSENTIF

- **Sales Home** adalah tempat alami untuk **breakdown komisi per-SKU/kategori** (model baru) + proyeksi saat lunas.
- Insentif **margin-aware** menjadikan **menyembunyikan HPP dari sales** makin penting (G2). Sales hanya lihat **insentif mereka**, bukan biaya.
- Konfigurasi rate insentif (entitas×kategori, diskon, margin cap) berada di **area manajemen (admin/manager)**, tak terlihat sales.
- Urutan kerja yang disarankan: **benahi pembeda peran + Sales Home dulu (kerangka)**, lalu pasang **engine + editor insentif** ke kerangka itu (sesuai pilihan user 5.c: bertahap).

---

## 6. KEPUTUSAN YANG DIBUTUHKAN (SEBELUM BUILD)

1. **Akses back-office untuk Sales** — setuju **cabut** landed cost/vendor bill/input tax/PO dari sales (tetap bisa lihat stok)? (Rekomendasi: ya, via permission matrix.)
2. **Faktur Pajak Jual** — apakah sales boleh menerbitkan, atau pindah ke finance/admin?
3. **Isi & prioritas Sales Home** — ranking: komisi · target · customer saya · penagihan · order · quick-create. Mana 3 teratas?
4. **Admin Home** — bangun "Ringkasan/Control Tower" baru, atau cukup tambah ringkasan di atas Master Data?
5. **KPI strip** — personalisasi per peran (sales lihat angkanya sendiri)?
6. **Pendekatan** — pembeda peran **berbasis konfigurasi** (permission + setting home) atau hardcode cepat?

---

# LANJUTAN 2026-08-15 (sesi repo `skskududu/KN`) — AUDIT DIJADIKAN GATE, LALU DIPERLUAS KE 6 PERAN

> Audit di atas (dokumen prosa) dulu **tidak punya penjaga**: temuannya diperbaiki, lalu
> kelas cacatnya bisa lahir kembali di layar berikutnya tanpa ada yang memerah. Sesi ini
> audit itu diubah menjadi **alat yang bisa dijalankan** (`scripts/audit_sales_roles_ux.py`)
> dan **didaftarkan sebagai gate** di `scripts/gate.sh`.

## 1. Cara alat ini menilai (semuanya bukti, tanpa daftar tebakan)
1. Menu yang terlihat per peran → `navStructure.js` + overlay `ROLE_NAV` lewat
   `check_nav_map.reachable_ids()` (SSOT yang sama dengan sidebar, Ctrl+K, dan deep-link),
   ditambah **tab hub** dari `config/hubTabs.js`.
2. Layar → berkas komponen dari `AppViewRouter.jsx`.
3. Endpoint layar itu → `axios.get(\`${API}/…\`)` di berkas layar **dan** komponen lokal yang
   ia impor (transitif 2 tingkat — bukan seluruh folder, supaya tak menuduh gara-gara berkas
   sebelahnya).
4. Endpoint **diketuk sungguhan** dengan token tiap peran. `403` = ditolak izin;
   `404/400/409` = izin LOLOS (dokumennya saja tak ada).

## 2. Dua kelas cacat yang dijaga
| Kelas | Arti | Status |
|---|---|---|
| **Layar mati** | SEMUA endpoint layar 403 → menu tak ada gunanya | MERAH sejak awal |
| **Panel mati** | SEBAGIAN 403 → layar terbuka, satu panel/dropdown kosong tanpa penjelasan | **MERAH sejak 2026-08-15** (dulu hanya kuning; 11 kasus nyata hidup di bawah warna kuning itu) |
| **Izin yatim** | Izin tulis ada di matriks, tak ada pintunya di layar | INDIKASI (butuh keputusan pemilik, bukan merah) |

## 3. Temuan 2026-08-15 (6 peran) & obatnya
Peran `admin` ikut diaudit sebagai **KONTROL** — ia berizin `*`, jadi temuan pada admin berarti
auditnya sendiri yang salah, bukan izinnya.

| Peran | Layar | Endpoint 403 | Obat (keputusan pemilik: beri izin baca) |
|---|---|---|---|
| finance | Aging Piutang | `/ar/aging`, `/ar/aging/{id}` | gerbang **izin** `accounting.view` ATAU `penalty.issue` (dulu `require_role(["manager"])`) |
| finance | Kasus Keuangan | `/suppliers` | `finance + supplier.view` + daftar opsional keluar dari `Promise.all` |
| warehouse | PR · RFQ · Retur Beli · Kontrabon | `/suppliers` | `warehouse + supplier.view` |
| manager | Karyawan | `/users` | `manager + user.view` (hanya BACA) |
| manager | Master Produk/Kategori/UOM | `/products/sales-owners` · `/admin/integrations` | dipagari **di kode** (`can(product.update)`; panel hanya di tab `integrations`) |
| warehouse | Retur Beli (detail) | `/gl/cash-accounts` | fetch dikunci `canApprove` |
| warehouse | Papan Stok · Kontrabon | `/internal-requests*` · `/bank-accounts` | sudah dipagari di kode → didaftarkan + **alamat pagarnya** |

Ikut ditutup: **INV-ROLE-01** di `ARAgingView` (`["admin","manager"].includes(role)` →
`can(perms,'penalty','issue')`) sehingga Finance yang berhak menerbitkan denda akhirnya
melihat tombolnya.

## 4. Kenapa laporan ini bisa dipercaya (anti salah-tuduh)
- Pembebasan "sudah dipagari di kode" berkunci **`(layar, path)`** + berisi **alamat pagarnya**;
  kunci global dulu memaafkan `/suppliers` di layar RFQ hanya karena wizard Kontrabon dipagari.
- `--self-test` (**9 kasus**) membuktikan penilaiannya bisa MENUDUH dan tidak salah-tuduh.
- Izin yatim: peta `(modul,aksi) → endpoint` dibaca statik dari `routers/*.py` (**prefix
  `APIRouter` ikut dibaca**) lalu dicocokkan wildcard dua arah dengan seluruh URL `${API}/…`
  di frontend → **58 tuduhan palsu turun menjadi 1 sinyal jujur** (`approval.approve`).
- Gate ini memakai `run_with_restore()` sehingga menjalankannya **tidak meninggalkan residu**.

## 5. Sisa pekerjaan yang jujur
`approval.approve` — `POST /approval-requests/{id}/approve|reject` ADA, produsennya TIDAK
(`create_approval_request()` nol pemanggil). Pilihan pemilik: hidupkan pintunya atau cabut
endpoint + izinnya. Lihat `plan.md` §STATUS F/F-5.
