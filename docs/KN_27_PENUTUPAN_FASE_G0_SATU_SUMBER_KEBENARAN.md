# KN_27 — PENUTUPAN FASE G-0: SATU SUMBER KEBENARAN KONFIGURASI

> Status: **✅ SELESAI & TERUJI** (sesi lanjutan repo `kamananabasa/kn`, 2026-07-26).
> Induk: `plan.md` §G-0 · `SESSION_HANDOFF.md` §0.7 · `KN_18` (PS-xx aturan configurable).
> Bukti: `bash scripts/gate.sh --full` **19/19 HIJAU** · `verify_data_integrity.py` **188 PASS / 0 FAIL / 0 WARN**
> · `backend/test_g0_config_poc.py` **115/0** · `testing_agent_v3` **iter_171 + iter_172** (0 bug).
> Aturan emas: **kode menang atas dokumen**.

---

## 1. Titik berhenti sesi sebelumnya

Backend FASE G-0 sudah lengkap (registry 98 entri, 14 endpoint `/api/config/*`, POC 115/0) dan
layar **Pusat Pengaturan** sudah tampil. Yang tertinggal ada di `frontend/src/App.js`:

```js
// FASE G-0 — deep-link ke Pusat Pengaturan dari 13 editor konfigurasi lama.
const [configFocus, setConfigFocus] = useState("");   // ← DIDEKLARASIKAN, TIDAK PERNAH DIPAKAI
```

`SettingsHub` sudah menerima prop `focusKey` dan mengekspor peta `LEGACY_DEEPLINK`, tetapi peta
itu **nol importer**. Artinya: janji "13 editor lama menunjuk ke satu sumber kebenaran" belum
ditepati sama sekali.

## 2. Keputusan pemilik (2026-07-26)

> *"Editor lama **dihapus**, semua diarahkan ke Pusat Pengaturan."*

Bukan read-only, bukan "tetap ada + tombol". **Dihapus.** Alasannya benar: selama dua form
masih bisa menulis kunci yang sama, keduanya pasti akan menyimpang cepat atau lambat.

## 3. Yang dikerjakan

### 3.1 Deep-link global `kn-open-config`
Mengikuti pola yang sudah terbukti di repo ini (`kn-open-palette` untuk Command Palette),
sehingga layar sedalam apa pun bisa menautkan **tanpa prop-drilling**.

```
openConfig({ key: "tax.ppn_rate" })          layar mana pun
        │  window.dispatchEvent("kn-open-config")
        ▼
useConfigDeepLink (hooks/)                    listener dipasang SEKALI
        │  navigate → view "settings-config" + setConfigFocus({key, group, nonce})
        ▼
App.js → AppViewRouter → <SettingsHub focusKey focusGroup focusNonce onFocusConsumed />
        │
        ▼
SettingsHub: pilih kelompok → isi pencarian → scroll → SOROT kartu 8 detik → lapor "sudah diserap"
```

Detail yang menentukan kualitasnya:
- **`nonce`** — menautkan ke kunci yang SAMA dua kali berturut-turut tetap memicu fokus ulang.
- **`onFocusConsumed`** — parent langsung membersihkan state, jadi membuka Pusat Pengaturan
  secara normal tidak "nyangkut" pada kunci lama.
- **`data-testid="cfg-card-<key>"` + `data-focused="1"`** — sorotan bisa diuji otomatis.

Berkas: `features/settings/config/configDeepLink.js` (tanpa dependensi, supaya layar yang cuma
menautkan tidak ikut menarik bundel Pusat Pengaturan yang di-`lazy()`), `hooks/useConfigDeepLink.js`.

### 3.2 Delapan permukaan editor lama dihapus

| # | Permukaan lama | Tindakan | Pengganti |
|---|---|---|---|
| 1 | `features/admin/SettingsPanel.jsx` (393 baris, 30 kunci) | **BERKAS DIHAPUS** + tab "Pengaturan" di `AdminView` dihapus | menu tetangga "Pusat Pengaturan" |
| 2 | `features/finance/TaxConfigPanel.jsx` (211 baris) | **BERKAS DIHAPUS** | `ConfigRedirectCard` di tab Konfigurasi Pusat Pajak |
| 3 | `features/hr/PayrollSetupView.jsx` (110 baris) | **BERKAS DIHAPUS** + route & menu "Setup Penggajian" dihapus | kelompok "SDM & Penggajian" |
| 4 | `features/purchasing/contracts/MakloonPolicyModal.jsx` | **BERKAS DIHAPUS** | tombol "Kebijakan Makloon" → `openConfig` |
| 5 | `features/admin/uom/ReceivingUomPolicyCard.jsx` | **BERKAS DIHAPUS** | `ConfigRedirectCard` di Konversi Satuan |
| 6 | `ToleranceCard` (UomConversionParts.jsx) | **KOMPONEN DIHAPUS** (CRUD aturan konversi TETAP) | idem |
| 7 | `EnforcementCard` (LotParts.jsx) | **KOMPONEN DIHAPUS** (daftar lot TETAP) | `ConfigRedirectCard` di layar Lot |
| 8 | Blok "Strategi Komisi" (IncentiveRatesEditor.jsx) | **BLOK DIHAPUS** (matriks rate insentif TETAP) | `ConfigRedirectCard` di CRM |

Helper mati ikut dibersihkan: `lotApi.saveSettings`, `makloonApi.updatePolicy`.
**Endpoint backend lama TIDAK dihapus** — mesin, skrip, dan 151 skrip uji lama masih memakainya;
yang hilang adalah *jalur tulis kedua dari UI*.

Prinsip pemisahan yang dipakai: **aturan sistem** pindah ke Pusat Pengaturan, **data master**
tetap di layarnya (rate insentif per entitas × kategori, aturan konversi satuan, daftar lot).

### 3.3 Wewenang: tidak ada peran yang kehilangan hak

Ini jebakan terbesar penggabungan editor. `PUT /api/config/values` dulu menuntut
`settings.manage` (admin saja), padahal endpoint lama punya wewenang yang berbeda-beda:

| Endpoint lama | Wewenang lama | Registry sekarang |
|---|---|---|
| `PUT /hr/payroll/settings` | `hr.manage_payroll` (admin + manager) | `permission=("hr","manage_payroll")` pada 18 kunci `hr.*` |
| `PUT /lots/settings` | `require_role(["manager"])` | `roles=("manager",)` pada 6 kunci `lot.*` |
| `PUT /supplier-contracts/policy` | `require_role(["admin","manager"])` | `roles=("manager",)` pada 7 kunci `makloon.*` |
| `PUT /uom-conversions/settings` | `uom.update` (admin) | `permission=("uom","update")` pada 5 kunci `uom.*` |
| `PUT /settings` · `/receiving/uom-settings` | `entity.update` / `settings.manage` (admin) | bawaan `settings.manage` |

Hasil terukur (diuji ulang oleh testing agent):

| Peran | Setting yang bisa diubah |
|---|---|
| admin | **96** (dari 98; 2 berstatus `not_used`) |
| manager | **31** = 6 `lot.*` + 7 `makloon.*` + 18 `hr.*` |
| sales | 0 |
| warehouse | 0 |

Menu "Pusat Pengaturan" kini terlihat untuk **admin + manager**. Manager melihat banner
`cfg-limited-rights` yang menjelaskan apa yang boleh ia ubah, dan tab "Koreksi Harga & Daftar
Dampak" disembunyikan karena ia tidak punya `product.update`.

`GET /api/config/registry` kini mengembalikan `caps` dan setiap entri punya `can_edit`, sehingga
**tombol yang terlihat bisa diklik = yang benar-benar diizinkan server** — persis kebalikan dari
patologi "tombol palsu" yang melahirkan FASE G-0.

### 3.4 Editor tabel terstruktur (agar penggabungan tidak menurunkan kualitas)

`TaxConfigPanel` yang dihapus punya satu keunggulan nyata: butir PPh bisa diubah baris-per-baris.
Kalau Pusat Pengaturan hanya menyediakan textarea JSON, penggabungan ini justru **merugikan user**.

Maka bentuk tabel kini dideskripsikan di registry (`row_shape` + `columns`) dan dirender oleh
`SettingTableEditor.jsx`:

| Setting | `row_shape` | Tampilan |
|---|---|---|
| `tax.pph_items` | `list` | baris: Aktif · Kode · Nama butir · Dasar hitung (enum) · Tarif (nonaktif bila basis `payroll`) |
| `hr.jkk_classes` | `list` | baris: Kelas risiko · Tarif JKK |
| `hr.ptkp_table` | `map` | pasangan Status PTKP → PTKP setahun |
| `approval.extra_levels` | `json` | struktur bertingkat — tetap JSON, dengan validasi & pesan jelas |

Registry menolak `row_shape="list"` tanpa `columns` (INV-CFG-03), jadi tabel baru tidak mungkin
lahir sebagai JSON mentah tanpa disengaja.

---

## 4. Guardrail: memperbaiki audit yang BERBOHONG

`scripts/audit_config_wiring.py` versi lama menilai "bisa diubah user" dengan **mencari nama
kunci secara harfiah di berkas frontend**. Sejak Pusat Pengaturan merender seluruh registry
secara **generik**, tidak ada satu pun nama kunci tertulis di kode frontend.

Terbukti saat editor lama dihapus:

```
SEBELUM perbaikan audit :  OK 24 · HIDDEN 77 · DEAD 4      ← 77 "temuan hantu"
SESUDAH perbaikan audit :  OK 96 · NOT_USED 9 · HIDDEN 0 · ORPHAN_UI 0 · DEAD 0
```

Perbaikan (mengikuti aturan repo #5 "baca dokumennya, jangan salin daftarnya"):
1. Audit **mengimpor `backend/config_registry.py`** untuk tahu kunci apa yang terkelola.
2. Lalu **membuktikan** rantai UI-nya utuh — `hub_wired()`: menu `settings-config` di
   `navStructure.js` → route di `AppViewRouter.jsx` → `<SettingsHub>` yang benar-benar memanggil
   `configApi.registry`/`effective` dan me-`map` daftarnya → `SettingEditor` yang punya
   `switch (entry.type)`. **Kalau satu mata rantai putus, seluruh kunci registry kembali HIDDEN.**
3. Daun DB yang lebih dalam dari registry (mis. `hr.ptkp_table.K1`) dicocokkan ke entri induknya,
   sehingga tidak lagi dilaporkan DEAD satu per satu.
4. `status="not_used"` + alasan tertulis diakui sebagai **SAH**, bukan pelanggaran.
5. Daftar berkas editor yang dulu **hardcode** diganti deteksi bentuk kode
   (`.saveSettings(`, `.put('/…/settings')`), dan komentar dibuang lebih dulu.

### 4.1 Cek baru: tidak boleh ada jalur tulis kedua
`legacy_config_writers()` mendeteksi berkas frontend yang masih menulis ke endpoint konfigurasi
lama. Kartu pengalih (`<ConfigRedirectCard …>` / `openConfig(…)`) sengaja **dikecualikan** — ia
MENGANTAR ke satu-satunya editor, bukan editor tandingan. Tanpa pengecualian ini kartu pengalih
kita sendiri akan dilaporkan sebagai "sumber kebenaran ganda" (temuan hantu jilid dua).

### 4.2 Bukti-merah wajib (aturan repo #6)
`python scripts/audit_config_wiring.py --self-test` membuktikan guardrail **bisa memerah**:

```
[1] keadaan nyata          : wired=True pelanggaran=0
[2] Hub diputus (simulasi) : HIDDEN=79 (harus > 0)
[3] penulis config lama    : 0 berkas (harus 0)
[4] penulis lama disuntik  : terdeteksi=1 (harus > 0)
[5] kartu pengalih murni   : tidak dihitung editor (benar)
SELF-TEST: PASS
```

---

## 5. Invarian baru — `INV-CFG-01 … 05`

Ditambahkan sebagai lapisan `layer_config_invariants` di `scripts/verify_data_integrity.py`
(**183 → 188 invarian**):

| Invarian | Menjaga apa |
|---|---|
| INV-CFG-01 | setiap setting terdeklarasi punya pembaca kode **dan** jalur ubah nyata (nol HIDDEN/ORPHAN_UI/DEAD); yang tak dipakai wajib `not_used` + alasan |
| INV-CFG-02 | rantai UI generik utuh: menu → route → `SettingsHub` → `SettingEditor` |
| INV-CFG-03 | registry konsisten: `active` wajib punya consumers · `not_used` wajib alasan · tipe tabel wajib punya bentuk baris/kolom |
| INV-CFG-04 | **tidak ada layar lain yang menulis konfigurasi** — satu-satunya jalur tulis UI adalah `PUT /api/config/values` |
| INV-CFG-05 | nilai tersimpan patuh batas registry (min/max/enum) — mesin tidak pernah menerima angka liar |

Dua gate baru di `scripts/gate.sh` (tahap statik, ~6s + ~11s):
```
config_wiring (INV-CFG-01/04, satu sumber kebenaran)   → audit_config_wiring.py --strict
config_wiring SELF-TEST (bukti-merah guardrail)        → audit_config_wiring.py --self-test
```

---

## 6. Bukti

```bash
cd /app
python seed_realistic.py
python backend/test_g0_config_poc.py            # 115 / 0
python scripts/audit_config_wiring.py           # OK 96 · NOT_USED 9 · sisanya 0
python scripts/audit_config_wiring.py --self-test
python scripts/verify_data_integrity.py         # 188 PASS / 0 FAIL / 0 WARN
python scripts/check_nav_map.py                 # PASS
python scripts/validate_compliance.py           # 24 PASS / 0 FAIL / 0 WARN
bash scripts/gate.sh --full                     # 19/19 HIJAU
bash scripts/rebuild_frontend.sh                # WAJIB setelah ubah frontend/src
```

`testing_agent_v3`:
- **iter_171** — backend 6/6 + 11 skenario UI lintas 4 peran · **0 bug**.
- **iter_172** — 8 user story sisa (kartu pengalih di 5 layar, menu & tab yang dihapus,
  editor tabel terstruktur, master data tetap hidup, regresi layar inti) · **0 bug**.

Satu catatan iter_172 ("tab Users tidak ditemukan") **diverifikasi ulang manual dan salah**:
ketujuh tab (`entities, customers, integrations, templates, permissions, audit, users`) hadir,
dan `admin-tab-settings-button` benar-benar sudah tidak ada.

---

## 7. Yang SENGAJA tidak dilakukan

1. **Endpoint konfigurasi lama tidak dihapus.** Mesin backend, `seed_realistic.py`, dan 151
   skrip uji masih memakainya. Menghapusnya = kerusakan luas tanpa manfaat tambahan; yang
   berbahaya adalah *UI kedua*, dan itu sudah hilang (dijaga INV-CFG-04).
2. **`scheduler.*` dan `integrations.*` (WhatsApp) tidak dipindahkan** ke Pusat Pengaturan.
   Keduanya belum ada di registry dan bentuknya bukan "aturan bisnis" melainkan konfigurasi
   job/kanal. Memaksakan pindah sekarang = registry setengah jadi. Dicatat sebagai kandidat
   perluasan registry berikutnya.
3. **`owner_role` tidak dihapus** walau kini tumpang tindih dengan `permission`. Ia masih
   dipakai untuk setting yang memang dikunci admin; menghapusnya berisiko melonggarkan RBAC
   secara diam-diam.

## 8. Utang teknis yang tertutup

| plan.md §G-12 | Status |
|---|---|
| #7 6 tombol palsu (ORPHAN_UI) | ✅ 0 |
| #8 6 dead settings | ✅ 0 (9 kunci PTKP ditandai `not_used` + alasan) |
| #9 31 hidden settings | ✅ 0 |
| #10 IA config tersebar 13 permukaan | ✅ satu pintu; 8 permukaan editor dihapus |
| #4 `block_over_remaining` separuh jalan (defect F1-08) | ✅ sudah tuntas (POC G-0 TEST 7) |

**Titik lanjut berikutnya: FASE G-1 — Fondasi Amandemen** (`plan.md` §G-1, urutan G-11 #1).
