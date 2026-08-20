"""PS-20 (D-14) — Katalog konfigurasi **PENEGAKAN MATRIKS PERSETUJUAN DIVISI**.

Semua sakelar di sini muncul otomatis di **Pusat Pengaturan → "Persetujuan & Ambang"**
(UI di-generate dari registry FASE G-0), sehingga pemilik dapat mengubah kebijakan
tanpa deploy — termasuk keputusan pemilik D-14: apakah penegakan berlaku untuk
dokumen yang MASIH MENUNGGU persetujuan (bawaan) atau hanya dokumen baru.

Konsumen nyata: `services/approval_matrix_service.py` (dipakai routers/rnd.py,
routers/purchase_requisitions.py, routers/special_orders.py, routers/approvals_matrix.py).
"""
from config_registry import E

G = ("global", "entity")
_MANAGER_TOO = ("manager",)
_SVC = "services/approval_matrix_service.py"

E("approval.matrix_enforcement", group="persetujuan", type="enum", default="enforce",
  options=({"value": "off", "label": "Nonaktif — matriks hanya jadi rujukan tampilan"},
           {"value": "warn", "label": "Peringatkan saja — dicatat, tetapi tetap boleh lanjut"},
           {"value": "enforce", "label": "Tegakkan — tolak bila bukan approver yang berhak"}),
  scopes=G,
  label="Ketegasan matriks persetujuan divisi",
  help="Matriks persetujuan R&D (ACC Desain, ACC Sample, PO Custom, Permintaan Pembelian) "
       "menetapkan siapa yang berhak menyetujui tiap tahap. Pengaturan ini menentukan "
       "apakah aturan itu benar-benar mengikat atau hanya ditampilkan sebagai rujukan.",
  impact="Pada 'Tegakkan', percobaan menyetujui oleh peran yang tidak berhak (atau oleh "
         "pengaju dokumen itu sendiri) akan DITOLAK dengan pesan jelas dan tercatat di "
         "jejak persetujuan. Pada 'Peringatkan saja', tindakan tetap lanjut namun ditandai "
         "pelanggaran di jejak sehingga bisa diaudit.",
  example="Sales mencoba meng-ACC desain → ditolak: hanya Manager (atau Direksi/Admin) yang berhak",
  consumers=(f"{_SVC}:settings", f"{_SVC}:evaluate", "routers/rnd.py",
             "routers/purchase_requisitions.py", "routers/special_orders.py"),
  related=("approval.matrix_scope", "approval.matrix_sod"), risk="high",
  roles=_MANAGER_TOO, permission=("rnd", "manage"))

E("approval.matrix_scope", group="persetujuan", type="enum", default="all_pending",
  options=({"value": "all_pending", "label": "Semua dokumen — termasuk yang masih menunggu persetujuan"},
           {"value": "new_only", "label": "Hanya dokumen baru — dokumen lama memakai cara lama"}),
  scopes=G,
  label="Dokumen mana yang ikut aturan baru",
  help="Saat aturan persetujuan diperketat, dokumen yang SUDAH mengantre bisa ikut aturan "
       "baru atau dibiarkan selesai dengan cara lama. Bawaannya 'Semua dokumen' sesuai "
       "keputusan pemilik, supaya tidak ada antrean yang lolos dari aturan.",
  impact="Pada 'Hanya dokumen baru', dokumen yang dibuat SEBELUM tanggal berlaku di bawah "
         "tidak diperiksa matriks (tetap bisa diselesaikan approver lama).",
  example="Ada 5 PR menunggu sejak minggu lalu → pada 'Semua dokumen', kelimanya kini wajib "
          "disetujui Manager yang bukan pengajunya",
  consumers=(f"{_SVC}:settings", f"{_SVC}:evaluate"),
  related=("approval.matrix_effective_from",), risk="high",
  roles=_MANAGER_TOO, permission=("rnd", "manage"))

E("approval.matrix_effective_from", group="persetujuan", type="text", default="",
  scopes=G,
  label="Tanggal mulai berlaku (dipakai bila memilih 'Hanya dokumen baru')",
  help="Format TTTT-BB-HH (contoh 2026-08-10). Dokumen yang dibuat sebelum tanggal ini "
       "dianggap dokumen lama. Bila dibiarkan kosong, sistem memakai tanggal hari ini.",
  impact="Mengubah tanggal ini menggeser garis batas antara dokumen lama dan baru.",
  example="Diisi 2026-08-10 → PR tanggal 9 Agustus tidak diperiksa, PR tanggal 10 Agustus diperiksa",
  consumers=(f"{_SVC}:settings", f"{_SVC}:evaluate"),
  related=("approval.matrix_scope",), risk="medium",
  roles=_MANAGER_TOO, permission=("rnd", "manage"))

E("approval.matrix_sod", group="persetujuan", type="bool", default=True, scopes=G,
  label="Pengaju tidak boleh menyetujui dokumennya sendiri",
  help="Pemisahan tugas (segregation of duties). Bila aktif, orang yang membuat/mengajukan "
       "dokumen tidak dapat menyetujui dokumen itu sendiri meskipun perannya berwenang.",
  impact="Pada posisi aktif, manager yang mengajukan PR-nya sendiri harus meminta manager "
         "lain atau Direksi/Admin untuk menyetujui.",
  example="Manager Dewi mengajukan PR bahan sample → Dewi tidak bisa menyetujuinya sendiri",
  consumers=(f"{_SVC}:evaluate", f"{_SVC}:is_requester"),
  related=("approval.matrix_enforcement",), risk="high",
  roles=_MANAGER_TOO, permission=("rnd", "manage"))

E("approval.po_custom_direksi_min", group="persetujuan", type="money", default=50000000,
  min=0, step=1000000, unit="Rp", scopes=G,
  label="Nilai PO Custom yang wajib naik ke Direksi (tingkat 2)",
  help="Pesanan khusus (PO Custom) selalu disetujui Manager lebih dulu. Bila nilainya "
       "mencapai angka ini, dibutuhkan persetujuan KEDUA dari Direksi (peran admin).",
  impact="Menaikkan angka membuat lebih banyak pesanan cukup disetujui Manager saja; "
         "menurunkannya membuat lebih banyak pesanan wajib menunggu Direksi.",
  example="Diisi 50.000.000 → pesanan khusus Rp 80 juta butuh Manager LALU Direksi",
  consumers=(f"{_SVC}:levels_for", "routers/special_orders.py"),
  related=("approval.matrix_enforcement",), risk="medium",
  roles=_MANAGER_TOO, permission=("rnd", "manage"))
