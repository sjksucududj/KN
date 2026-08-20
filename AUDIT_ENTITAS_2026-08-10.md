# LAPORAN PENELUSURAN — Pengaturan Entitas, Pemilihan/Penambahan Entitas, & Akun Tertaut Entitas

> Tanggal: 2026-08-10 · Repo: `janabagganajana/kn` (dipulihkan ke `/app`)
> Metode: pembacaan kode + **probe empiris** terhadap API yang berjalan
> (`/app/probe_entity_flow.py`, `/app/probe_entity_flow2.py`) — semua temuan di bawah
> punya bukti status/respons nyata, bukan dugaan.

---

## 1. Peta kode yang mengurus entitas

### Backend
| Berkas | Peran |
|---|---|
| `routers/entities.py` (81 baris) | `GET/POST/PATCH/DELETE /api/entities` — master entitas legal (PT/CV) |
| `services/entity_provisioning_service.py` | `provision_entity()`: validasi unik `short_name` + `doc_prefix`, isi default, seed CoA bersama, buat penanda config per-entitas |
| `services/entity_context_service.py` | `PRIMARY_ENTITY_ID=ent_ksc`, `CROSS_ENTITY_ROLES={admin,manager}`, `build_entity_context()`, migrasi idempotent `ensure_entity_defaults/ensure_user_entities` |
| `entity_scope.py` | Inti scoping: registry `SCOPE_FIELD` per koleksi, dependency `entity_ctx`, `resolve_list_scope`, `stamp_entity`, `assert_entity_access` |
| `core_utils.py` | `next_doc_number()` + `entity_code()` — nomor dokumen `PREFIX/SO-00001` per entitas (pakai `doc_prefix`) |
| `routers/users.py` | `GET/POST/PATCH /api/users` — akun + `home_entity_id` & `allowed_entity_ids` |
| `routers/auth.py` | Login mengembalikan `entity_context`; `/auth/me` & `/auth/context` menghormati header `X-Entity-Id` |
| `permissions_config.py` | `entity: [view, create, update, delete]` (admin) · manager hanya `view` |

### Frontend
| Berkas | Peran |
|---|---|
| `components/EntitySwitcher.jsx` | Pemilih entitas di TopBar (+ opsi "Semua Entitas"); terkunci untuk sales/gudang |
| `services/apiClient.js` | `setActiveEntity()` → header `X-Entity-Id` global |
| `App.js` | State `selectedEntity` (localStorage `kn_entity`) + `entityContext` (`kn_entity_ctx`) |
| `features/admin/AdminView.jsx` | **Satu-satunya** tempat entitas & akun dibuat: tab `Entities` dan `Users` di dalam hub *Pengaturan & Master Data → Master Data & Audit* |
| `hooks/useAppActions.js` | `adminCreate/adminPatch/adminDelete` generik (POST/PATCH/DELETE `/api/<resource>`) |
| `components/EntityBadge.jsx`, `utils/entityLabel.js` | Lencana & penormal label entitas (tambalan karena bentuk data `/api/entities` ≠ `/auth/context`) |

---

## 2. Temuan cacat (dengan bukti)

| # | Temuan | Bukti |
|---|---|---|
| 1 | **Nomor dokumen bisa tabrakan antar-PT** — `PATCH /api/entities/{id}` tidak memvalidasi keunikan `doc_prefix`/`short_name` | `PATCH doc_prefix → "KSC"` = **200**; kini 2 entitas ber-prefix `KSC` → `KSC/SO-00001` bisa terbit di dua PT (sequence per `entity_id`) |
| 2 | **Cache kode entitas tak pernah dibersihkan** (`_ENTITY_CODE_CACHE`) | Ganti `doc_prefix` tidak berlaku pada proses yang sedang jalan sampai backend restart |
| 3 | **Tombol "Deactivate" pada tab Users rusak** | FE memanggil `DELETE /api/users/{id}` → **405 Method Not Allowed** (endpoint tidak ada) |
| 4 | **Tombol "Update" palsu** untuk entities/users (PATCH status ke nilai yang sama) tetapi memunculkan "berhasil diupdate" | `AdminView.jsx` baris 381 |
| 5 | **Tidak ada formulir ubah** entitas maupun akun | Nama legal/NPWP/prefix/mode pajak/logo & role/entitas/password hanya bisa diubah lewat API mentah |
| 6 | **Email akun bisa duplikat lewat PATCH** | `PATCH /users` email → email admin = **200**; kini 2 akun ber-email `admin@kainnusantara.id` (login `find_one({email})` → ambigu) |
| 7 | **Turun jabatan tidak mencabut akses lintas-PT** | admin→sales: `allowed_entity_ids` tetap `[ent_ksc, ent_kanda, ent_baru]`, `can_switch_entity=true` |
| 8 | **Entitas nonaktif tetap muncul di pemilih** & bila dipilih sistem **diam-diam** jatuh ke entitas home | `X-Entity-Id=<ent nonaktif>` → `active_entity_id=ent_ksc`; `POST /customers` → `entity_id=ent_ksc` |
| 9 | **Mode "Semua Entitas" menulis diam-diam ke home** | `POST /customers` dgn `X-Entity-Id: all` → `entity_id=ent_ksc`, tanpa peringatan apa pun di UI |
| 10 | **Nonaktifkan entitas tanpa pagar** | Entitas yang masih dipakai user aktif tetap dinonaktifkan; sales-nya **masih bisa login & bekerja** di PT mati, sedangkan admin kehilangan PT itu dari switcher |
| 11 | **Pembuatan entitas tidak menuntun** | Hasil `provisioning` dibuang FE; notifikasi "entities dibuat: **undefined**" (`adminCreate` membaca `data.name`, entitas hanya punya `legal_name`); form tidak direset; field `currency/fiscal_year_start/parent_entity_id/is_group/coa_template/incentive_payer/numbering_scheme` didukung backend tetapi **tidak ada di UI**; setelah PT dibuat tidak ada penunjuk langkah lanjutan |
| 12 | **Bentuk data entitas tidak konsisten** | `/api/entities` = dokumen mentah (`legal_name`), `/auth/context` = ringkasan (`name`,`code`) → sudah melahirkan tambalan `utils/entityLabel.js` + komentar bug di ≥6 berkas |
| 13 | **Tidak ada layar hubungan entitas↔akun** | Daftar user tidak menampilkan PT-nya, tidak ada filter per PT, `GET /users` mengabaikan `?entity_id` dan dibatasi 100 baris tanpa paging |

### Yang SUDAH benar (jangan dirusak)
- Lapisan scoping `entity_scope.py` rapi & terpusat (registry koleksi, anti-IDOR, mode `all`).
- Validasi unik saat **create** entitas (409) & `home_entity_id` ngawur ditolak (400).
- RBAC: manager/sales **403** saat mencoba `POST /entities`.
- Sales/gudang terkunci ke entitasnya (`can_switch_entity=false`) dan `X-Entity-Id=all` dari mereka diabaikan.
- Provisioning mengisi default + CoA bersama + penanda config per entitas.
