"""FASE G-9 — Katalog konfigurasi **PUSAT KASUS KEUANGAN** (Finance Exception Desk).

Kasus keuangan adalah tempat uang "nyangkut": salah transfer, bayar dobel, giro ditolak,
dana tak dikenal. Aturannya tidak boleh jadi angka sihir di dalam kode — kalau SLA-nya
24 jam atau ambang persetujuannya Rp 5 juta, pemilik usaha harus bisa mengubahnya sendiri
dari Pusat Pengaturan tanpa menunggu rilis baru.

Semua kunci di sini dikonsumsi `services/finance_case_service.py` (+ `_actions`).
"""
from config_registry import E

G = ("global", "entity")

E("case.sla_hours", group="kasus", type="int", default=24, min=1, max=720, step=1,
  unit="jam", scopes=G,
  label="Batas waktu penyelesaian kasus (SLA)",
  help="Berapa jam sebuah kasus keuangan boleh menganggur sebelum dianggap terlambat. "
       "Kasus yang lewat batas ditandai merah di Inbox dan bisa dinaikkan ke atasan.",
  impact="Semakin kecil, semakin cepat kasus terlihat terlambat — antrean jadi lebih disiplin.",
  example="SLA 24 jam · kasus dibuka kemarin 09:00 dan belum selesai → ditandai TERLAMBAT",
  consumers=("services/finance_case_service.py:sla_of",), risk="low",
  related=("case.sla_hours_high", "case.escalate_on_sla_breach"))

E("case.sla_hours_high", group="kasus", type="int", default=8, min=1, max=720, step=1,
  unit="jam", scopes=G,
  label="Batas waktu untuk kasus bernominal besar",
  help="Kasus yang nominalnya di atas 'Ambang kasus bernominal besar' memakai batas waktu "
       "yang lebih pendek karena risikonya lebih besar.",
  impact="Uang besar tidak boleh menunggu selama uang kecil.",
  example="SLA besar 8 jam · kasus Rp 50.000.000 dibuka 09:00 → terlambat setelah 17:00",
  consumers=("services/finance_case_service.py:sla_of",), risk="low",
  related=("case.high_amount_threshold",))

E("case.high_amount_threshold", group="kasus", type="money", default=10000000,
  min=0, step=500000, unit="Rp", scopes=G,
  label="Ambang kasus bernominal besar",
  help="Kasus dengan nominal dipertaruhkan di atas angka ini dianggap prioritas tinggi: "
       "batas waktunya lebih pendek dan urutannya di atas.",
  impact="Menentukan kasus mana yang naik ke atas antrean.",
  example="Ambang Rp 10.000.000 · kasus Rp 25.000.000 → prioritas TINGGI",
  consumers=("services/finance_case_service.py:priority_of",), risk="low")

E("case.require_evidence", group="kasus", type="bool", default=True, scopes=G,
  label="Wajib lampirkan bukti sebelum kasus ditutup",
  help="Untuk jenis kasus yang menyangkut klaim pihak lain (mis. transfer dari nama pihak "
       "ketiga, transfer ke rekening pribadi karyawan), penyelesaian tidak boleh dilakukan "
       "tanpa lampiran bukti seperti foto bukti transfer atau surat pernyataan.",
  impact="Kalau dinyalakan, tombol Selesaikan menolak kasus tanpa lampiran.",
  example="Nyala · kasus 'Transfer dari nama pihak ketiga' tanpa lampiran → ditolak",
  consumers=("services/finance_case_service.py:_assert_evidence",), risk="medium")

E("case.require_approval_above", group="kasus", type="money", default=5000000,
  min=0, step=500000, unit="Rp", scopes=G,
  label="Penyelesaian di atas nominal ini wajib disetujui",
  help="Kasus yang penyelesaiannya memindahkan uang lebih besar dari angka ini hanya boleh "
       "ditutup oleh peran penyetuju (atau admin). Di bawahnya, petugas keuangan boleh "
       "menutup sendiri.",
  impact="Menaikkan angka ini mempercepat kerja tetapi mengurangi kontrol berlapis.",
  example="Ambang Rp 5.000.000 · refund Rp 7.500.000 → wajib manager/admin",
  consumers=("services/finance_case_service.py:_assert_authority",), risk="high",
  related=("case.approver_role", "case.refund_max_amount"))

E("case.approver_role", group="kasus", type="enum", default="manager", scopes=G,
  options=[{"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin"}],
  label="Peran penyetuju penyelesaian kasus",
  help="Siapa yang berwenang menutup kasus yang nominalnya di atas ambang persetujuan.",
  impact="Menentukan siapa yang boleh menutup kasus besar.",
  example="Manager · refund Rp 7.500.000 hanya bisa ditutup manager atau admin",
  consumers=("services/finance_case_service.py:_assert_authority",), risk="high")

E("case.refund_max_amount", group="kasus", type="money", default=25000000,
  min=0, step=1000000, unit="Rp", scopes=G,
  label="Batas pengembalian dana oleh penyetuju",
  help="Nominal pengembalian dana (refund) terbesar yang masih boleh diputus peran "
       "penyetuju. Di atas ini wajib admin/direksi. 0 = tanpa batas.",
  impact="Menjaga uang keluar besar tetap di tangan pemilik keputusan tertinggi.",
  example="Batas Rp 25.000.000 · refund Rp 40.000.000 oleh manager → ditolak, harus admin",
  consumers=("services/finance_case_service.py:_assert_authority",), risk="high")

E("case.duplicate_window_days", group="kasus", type="int", default=7, min=1, max=90, step=1,
  unit="hari", scopes=G,
  label="Jendela deteksi pembayaran dobel",
  help="Dua kwitansi pelanggan yang sama dengan nominal sama di dalam jendela hari ini "
       "dicurigai sebagai pembayaran dobel dan otomatis dibuatkan kasus.",
  impact="Semakin lebar, semakin banyak dugaan dobel yang tertangkap (bisa lebih banyak alarm).",
  example="Jendela 7 hari · Rp 3.750.000 dari pelanggan yang sama pada 1 & 5 Juli → 1 kasus",
  consumers=("services/finance_case_service.py:scan",), risk="medium")

E("case.holding_case_after_days", group="kasus", type="int", default=3, min=0, max=365, step=1,
  unit="hari", scopes=G,
  label="Titipan dana menganggur berapa hari sebelum jadi kasus",
  help="Dana masuk tak dikenal yang ditampung di akun titipan (Rekonsiliasi Bank) akan "
       "otomatis menjadi kasus keuangan setelah menganggur selama ini — supaya tidak ada "
       "uang yang terlupakan tanpa penanggung jawab.",
  impact="Semakin kecil, semakin cepat uang tak dikenal ditindaklanjuti orang.",
  example="3 hari · titipan Rp 5.131.200 masuk 26 Juli, pada 29 Juli otomatis jadi kasus",
  consumers=("services/finance_case_service.py:scan",), risk="medium",
  related=("bank.holding_max_age_days",))

E("case.auto_bank_charge_max", group="kasus", type="money", default=50000, min=0, step=5000,
  unit="Rp", scopes=G,
  label="Selisih biaya bank yang boleh diselesaikan otomatis",
  help="Kalau uang yang sampai lebih kecil dari tagihan hanya sebesar biaya transfer bank "
       "(di bawah angka ini), kasus boleh diselesaikan tanpa persetujuan: selisihnya "
       "dibebankan ke Beban Administrasi Bank.",
  impact="Membebaskan keuangan dari kasus receh, tetapi tetap berjurnal dan berlabel.",
  example="Batas Rp 50.000 · kurang Rp 6.500 karena biaya transfer → selesai otomatis",
  consumers=("services/finance_case_service.py:policy",
            "services/finance_case_service.py:resolve"), risk="medium")

E("case.escalate_on_sla_breach", group="kasus", type="bool", default=True, scopes=G,
  label="Naikkan kasus terlambat ke atasan",
  help="Kasus yang melewati batas waktu dikirim sebagai notifikasi bertingkat ke manager "
       "lalu admin, memakai mesin eskalasi yang sama dengan alert operasional.",
  impact="Kalau dimatikan, kasus terlambat hanya terlihat di Inbox tanpa memberi tahu siapa pun.",
  example="Nyala · kasus lewat 24 jam → notifikasi 'ESKALASI: Kasus keuangan terlambat'",
  consumers=("services/finance_case_service.py:scan",), risk="low")

E("case.auto_scan_enabled", group="kasus", type="bool", default=True, scopes=G,
  label="Buat kasus otomatis dari temuan sistem",
  help="Sistem memindai titipan dana yang menganggur dan pembayaran yang terlihat dobel, "
       "lalu membuat kasusnya sendiri. Kalau dimatikan, kasus hanya bisa dibuat manual.",
  impact="Mematikan ini membuat antrean bergantung pada kerajinan orang mengetik kasus.",
  example="Nyala · pemindai harian menemukan 1 titipan tua → 1 kasus baru bernomor KSC/CASE-00001",
  consumers=("services/finance_case_service.py:scan",), risk="medium")
