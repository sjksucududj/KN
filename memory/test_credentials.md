# Test Credentials — Kain Nusantara (WMS/ERP)

> Ditulis ulang tiap clone: berkas ini **di-.gitignore**, jadi kontainer baru selalu datang kosong.
> Semua akun berasal dari `python seed_realistic.py` (data demo). **Password sama untuk semua:**
> `demo12345`

| Peran | Email | Catatan |
|---|---|---|
| Admin | `admin@kainnusantara.id` | Budi Santoso — akses penuh (Pengaturan · Master · semua modul) |
| Manajer | `manager@kainnusantara.id` | Dewi Rahayu — persetujuan, laporan |
| Admin Sales | `salesadmin@kainnusantara.id` | Rina Kusumawati — Meja Admin Sales |
| Finance | `finance@kainnusantara.id` | Hendra Wijaya — Meja Finance (uang masuk, pajak) |
| Sales | `sales@kainnusantara.id` | Ayu Permatasari (juga `sales2@`, `sales3@`) |
| Gudang | `warehouse@kainnusantara.id` | Eko Prasetyo (juga `warehouse2@`) |
| Sales **berpagar lini printing** (FASE L) | `dewi.printing@kainnusantara.id` | `allowed_line_codes=["printing"]` — hanya melihat pekerjaan lini printing |
| Manajer warisan (uji "cek kenyataan peran") | `adminsales.lama@kainnusantara.id` | peran `manager` tetapi jejaknya Admin Sales |

## Catatan penting untuk agen uji
* Layar masuk: `data-testid="login-email-input"`, `login-password-input`, tombol submit di
  `LoginScreen.jsx` (lihat `data-testid` di berkas itu).
* Setelah masuk, **pilih badan usaha** dulu bila diminta (PT Kain Suka Cita "KSC" / CV Kanda Suka)
  — mode "Semua Entitas" sengaja **hanya-lihat** (aksi tulis dijawab 409 dengan kalimat menuntun).
* `allowed_line_codes: []` berarti **SEMUA lini** (bukan "tidak boleh apa pun").
* Basis data uji: `test_database` (lihat `backend/.env`). Pulihkan data demo kapan pun dengan
  `python seed_realistic.py`.
