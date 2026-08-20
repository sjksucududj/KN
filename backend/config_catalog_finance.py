"""FASE G-1 — Katalog konfigurasi **AMANDEMEN DOKUMEN**.

Pemilik menegaskan: *“jangan hardcode aturan”*. Karena itu seluruh ambang yang
menentukan kapan sebuah koreksi boleh langsung jalan dan kapan wajib disetujui
didaftarkan di registry — bisa diubah admin dari Pusat Pengaturan tanpa deploy,
lengkap dengan penjelasan awam, contoh angka, dan riwayat perubahan.

Semua kunci di sini dikonsumsi oleh `services/amendment_service.py`.
"""
from config_registry import E

G = ("global", "entity")

E("amendment.approval_threshold_amount", group="amandemen", type="money",
  default=5000000, min=0, max=100000000000, step=1000000, unit="Rp", scopes=G,
  label="Nilai koreksi yang wajib disetujui",
  help="Bila DAMPAK sebuah koreksi (selisih rupiah, tanpa tanda) mencapai angka ini, "
       "koreksi tidak langsung jalan — harus disetujui dulu.",
  impact="Menentukan koreksi mana yang boleh langsung diterapkan pengusul dan mana "
         "yang masuk antrean persetujuan.",
  example="Ambang Rp 5.000.000 · koreksi menurunkan tagihan Rp 7.500.000 → WAJIB disetujui",
  consumers=("services/amendment_service.py:evaluate_policy",), risk="high",
  related=("amendment.approval_threshold_pct", "amendment.approver_role"))

E("amendment.approval_threshold_pct", group="amandemen", type="pct",
  default=5.0, min=0, max=100, step=0.5, unit="%", scopes=G,
  label="Persentase koreksi yang wajib disetujui",
  help="Selain ambang rupiah, koreksi juga wajib disetujui bila mengubah nilai dokumen "
       "lebih besar dari persen ini. Cukup salah satu terlampaui.",
  impact="Menjaring koreksi kecil-nilai pada dokumen kecil yang secara persentase besar.",
  example="Ambang 5% · dokumen Rp 20.000.000 turun Rp 2.000.000 (10%) → WAJIB disetujui",
  consumers=("services/amendment_service.py:evaluate_policy",), risk="high",
  related=("amendment.approval_threshold_amount",))

E("amendment.approver_role", group="amandemen", type="enum", default="manager",
  options=({"value": "manager", "label": "Manager"},
           {"value": "admin", "label": "Admin / Direksi"}),
  scopes=G,
  label="Siapa yang menyetujui koreksi",
  help="Peran yang berwenang menyetujui koreksi biasa. Koreksi bernilai sangat besar "
       "tetap naik ke admin (lihat 'Nilai koreksi yang wajib disetujui admin').",
  impact="Menentukan antrean persetujuan koreksi masuk ke peran yang mana.",
  example="'manager' → koreksi Rp 7.500.000 menunggu persetujuan manager",
  consumers=("services/amendment_service.py:evaluate_policy",), risk="high")

E("amendment.admin_approval_above", group="amandemen", type="money",
  default=50000000, min=0, max=100000000000, step=5000000, unit="Rp", scopes=G,
  label="Nilai koreksi yang wajib disetujui admin",
  help="Di atas angka ini persetujuan manager tidak cukup — harus admin/direksi.",
  impact="Menaikkan tingkat persetujuan untuk koreksi bernilai besar.",
  example="Ambang Rp 50.000.000 · koreksi Rp 80.000.000 → hanya admin yang bisa menyetujui",
  consumers=("services/amendment_service.py:evaluate_policy",), risk="high",
  related=("amendment.approver_role",))

E("amendment.dual_control", group="amandemen", type="bool", default=True, scopes=G,
  label="Pengusul tidak boleh menyetujui usulannya sendiri",
  help="Kontrol ganda: orang yang mengajukan koreksi tidak boleh menjadi penyetujunya, "
       "walaupun perannya berwenang.",
  impact="Mencegah satu orang mengubah angka uang sendirian tanpa mata kedua.",
  example="Aktif · manager mengajukan koreksi → harus manager/admin LAIN yang menyetujui",
  consumers=("services/amendment_service.py:decide",), risk="high")

E("amendment.require_note_above", group="amandemen", type="money",
  default=10000000, min=0, max=100000000000, step=1000000, unit="Rp", scopes=G,
  label="Nilai koreksi yang wajib disertai penjelasan tertulis",
  help="Label alasan saja tidak cukup untuk koreksi besar — pengusul wajib menulis "
       "penjelasan bebas yang tersimpan permanen.",
  impact="Menolak pengajuan koreksi besar yang tidak menyertakan penjelasan.",
  example="Ambang Rp 10.000.000 · koreksi Rp 12.000.000 tanpa catatan → DITOLAK",
  consumers=("services/amendment_service.py:propose",), risk="medium")

E("amendment.issued_doc_policy", group="amandemen", type="enum", default="note_only",
  options=({"value": "note_only",
            "label": "Hanya lewat Nota Kredit/Debit (dokumen terbit tidak pernah diubah)"},
           {"value": "allow_re_derive",
            "label": "Boleh menghitung ulang dokumen terbit (TIDAK disarankan)"}),
  scopes=G,
  label="Cara mengoreksi dokumen yang sudah terbit",
  help="Dokumen yang sudah terbit (sudah difakturkan/dibayar) idealnya tidak pernah "
       "diubah angkanya. Koreksinya diterbitkan sebagai Nota Kredit (nilai turun) atau "
       "Nota Debit (nilai naik) yang tertaut ke dokumen asal.",
  impact="Menentukan apakah koreksi menghasilkan nota baru atau menimpa dokumen asal.",
  example="'note_only' · SO sudah dibayar lalu harga dikoreksi turun Rp 500.000 → terbit Nota Kredit",
  consumers=("services/amendment_service.py:evaluate_policy",), risk="high")
