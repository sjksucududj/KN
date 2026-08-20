"""FASE G-5 — Katalog konfigurasi **UNLOCK PERIODE TERTUTUP**.

Pemilik: *"Bangun izin buka periode tertutup yang wajib dua orang dan menutup
sendiri saat waktunya habis."* Semua ambang di sini dikonsumsi oleh
`services/period_unlock_service.py` (jendela unlock & batas mundur), sehingga
dapat diubah admin dari Pusat Pengaturan tanpa deploy.
"""
from config_registry import E

G = ("global", "entity")

E("periode.unlock_window_hours", group="keuangan-dasar", type="int",
  default=24, min=1, max=168, step=1, unit="jam", scopes=G,
  label="Lama jendela buka periode (jam)",
  help="Setelah usul buka periode DISETUJUI, periode terbuka HANYA selama sekian jam. "
       "Lewat batas itu sistem menutup sendiri (auto-reclose) — tidak perlu ditutup manual.",
  impact="Menentukan berapa lama koreksi mundur boleh diposting sebelum periode terkunci lagi.",
  example="24 jam · disetujui 09:00 → periode terkunci lagi otomatis besok 09:00",
  consumers=("services/period_unlock_service.py:approve_request",
             "services/period_unlock_service.py:reclose_expired"),
  risk="high", requires_reason=True,
  related=("periode.max_days_after_close",))

E("periode.max_days_after_close", group="keuangan-dasar", type="int",
  default=7, min=0, max=3650, step=1, unit="hari", scopes=G,
  label="Batas mundur usul buka periode (hari setelah tutup)",
  help="Usul buka periode hanya boleh diajukan bila periode ditutup TIDAK lebih lama dari "
       "sekian hari yang lalu. Isi 0 untuk tanpa batas (tidak disarankan).",
  impact="Mencegah membuka periode lama yang laporannya sudah beredar/diaudit.",
  example="7 hari · periode ditutup 20 hari lalu → usul DITOLAK (di luar batas mundur)",
  consumers=("services/period_unlock_service.py:request_unlock",),
  risk="high",
  related=("periode.unlock_window_hours",))
