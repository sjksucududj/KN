# tests/archive — skrip uji lama (dipindah dari akar repo, sesi 2026-08-11)

**Kenapa ada folder ini.** Akar repo sempat menampung **124 berkas** `backend_test_*.py`,
`test_*_poc.py`, `vendor_bill_*.py`, dan `verify_iter210_fixes.py` — sisa POC & uji
per-fase dari puluhan sesi. Akibatnya akar repo tidak lagi bisa dibaca sekilas: berkas
yang MASIH dipakai gate (mis. `backend/test_core_e0_isolation_poc.py`) tenggelam di
antara berkas yang sudah tidak pernah dijalankan lagi.

**Yang dipindah ke sini:** skrip yang **tidak** dirujuk `scripts/gate.sh` maupun
`scripts/*` mana pun (diperiksa satu per satu sebelum dipindah — nol rujukan).
Skrip ini **tidak dihapus** karena masih berguna sebagai catatan sejarah: ia
menunjukkan bagaimana sebuah fase dibuktikan pada waktunya.

**Yang TIDAK dipindah (masih aktif, jangan dipindah):**
- `backend/test_core_*_poc.py` — POC fase yang dijalankan `gate.sh`
  (E-0, E-3, E-4, **E-5**, F0-C, dst).
- `backend/tests/*` — pytest resmi (mis. `test_g6_poc.py`, `test_g6b_poc.py`).
- `tests/*.py` di luar folder `archive/` ini.
- `seed_realistic.py`, `seed_r0_demo.py`, `seed_returnable_demo.py` di akar repo.

**Menjalankan ulang skrip arsip.** Sebagian besar memakai jalur relatif dari akar
repo (`/app`) dan mengimpor `backend/`. Jalankan dari akar:

    cd /app && python tests/archive/<nama_berkas>.py

Bila gagal karena impor, jalankan dari `backend/`:

    cd /app/backend && python ../tests/archive/<nama_berkas>.py

Daftar uji yang **aktif** ada di `tests/INDEX.md`; daftar alat di `scripts/INDEX.md`.
