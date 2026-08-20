"""FASE G-8 — Katalog konfigurasi **REKONSILIASI BANK**.

Pemilik menegaskan: *"jangan hardcode aturan"*. Skor pencocokan mutasi bank adalah
contoh paling gampang jadi angka sihir di dalam kode ("kok ini dianggap cocok?").
Karena itu SELURUH bobot & ambang didaftarkan di registry: bisa diubah admin dari
Pusat Pengaturan, punya penjelasan awam, contoh angka, dan riwayat perubahan.

Semua kunci di sini dikonsumsi oleh `services/bank_recon_service.py`.
"""
from config_registry import E

G = ("global", "entity")

E("bank.match_weight_amount", group="bank", type="int", default=40, min=0, max=100, step=5,
  unit="poin", scopes=G,
  label="Poin bila nominal sama",
  help="Berapa poin diberikan saat nominal mutasi bank sama dengan nominal transaksi di buku. "
       "Nominal adalah petunjuk terkuat, jadi bobotnya paling besar.",
  impact="Menaikkan angka ini membuat pasangan yang nominalnya sama lebih mudah dianggap cocok.",
  example="Bobot 40 · transfer Rp 12.500.000 = kwitansi Rp 12.500.000 → +40 poin",
  consumers=("services/bank_recon_service.py:score_pair",), risk="medium",
  related=("bank.auto_match_min_score",))

E("bank.match_weight_date", group="bank", type="int", default=20, min=0, max=100, step=5,
  unit="poin", scopes=G,
  label="Poin bila tanggal berdekatan",
  help="Poin penuh bila tanggalnya sama, lalu berkurang setiap hari selisih sampai batas "
       "'Selisih hari yang masih wajar'.",
  impact="Membedakan dua kwitansi bernominal sama: yang tanggalnya paling dekat menang.",
  example="Bobot 20 · jendela 3 hari · selisih 1 hari → +13 poin",
  consumers=("services/bank_recon_service.py:score_pair",), risk="medium",
  related=("bank.date_window_days",))

E("bank.match_weight_ref", group="bank", type="int", default=25, min=0, max=100, step=5,
  unit="poin", scopes=G,
  label="Poin bila nomor referensi cocok",
  help="Poin bila berita transfer menyebut nomor dokumen kita (mis. SO-0007 / nomor kwitansi). "
       "Setengah poin bila hanya sebagian angkanya sama.",
  impact="Membuat pelanggan yang menulis nomor pesanan di berita transfer langsung tercocok otomatis.",
  example="Bobot 25 · berita transfer 'BYR SO-0007' & kwitansi untuk SO-0007 → +25 poin",
  consumers=("services/bank_recon_service.py:score_pair",), risk="medium")

E("bank.match_weight_name", group="bank", type="int", default=15, min=0, max=100, step=5,
  unit="poin", scopes=G,
  label="Poin bila nama pengirim mirip",
  help="Poin bila nama pada berita transfer mirip nama pelanggan/keterangan transaksi buku. "
       "Kemiripan dihitung, jadi 'PT MAJU JAYA' tetap dikenali walau ditulis 'PT MAJU JAYA TBK'.",
  impact="Menolong saat pelanggan tidak menulis nomor dokumen apa pun.",
  example="Bobot 15 · 'TRSF E-BANKING CR PT MAJU JAYA' vs pelanggan 'PT Maju Jaya' → +15 poin",
  consumers=("services/bank_recon_service.py:score_pair",), risk="medium")

E("bank.auto_match_min_score", group="bank", type="int", default=80, min=0, max=200, step=5,
  unit="poin", scopes=G,
  label="Skor minimal untuk dicocokkan otomatis",
  help="Pasangan dengan skor mencapai angka ini ditautkan otomatis tanpa bertanya. "
       "Naikkan bila Anda ingin lebih hati-hati.",
  impact="Terlalu rendah = salah cocok; terlalu tinggi = semuanya harus dikerjakan manual.",
  example="Ambang 80 · pasangan berskor 85 → langsung tertaut; berskor 70 → jadi usulan",
  consumers=("services/bank_recon_service.py:auto_match",), risk="high",
  related=("bank.suggest_min_score",))

E("bank.suggest_min_score", group="bank", type="int", default=60, min=0, max=200, step=5,
  unit="poin", scopes=G,
  label="Skor minimal untuk ditawarkan sebagai usulan",
  help="Di bawah ambang otomatis tetapi mencapai angka ini → muncul sebagai usulan berperingkat "
       "yang bisa Anda terima 1 klik. Di bawahnya: murni manual.",
  impact="Menentukan seberapa banyak usulan yang muncul di layar.",
  example="Ambang usulan 60 · pasangan berskor 62 → tampil sebagai usulan",
  consumers=("services/bank_recon_service.py:auto_match",
             "services/bank_recon_service.py:candidates"), risk="medium")

E("bank.date_window_days", group="bank", type="duration", default=3, min=0, max=60, step=1,
  unit="hari", scopes=G,
  label="Selisih hari yang masih wajar",
  help="Transfer bisa tercatat di bank sehari-dua setelah dibukukan. Di luar jendela ini "
       "pasangan tidak dipertimbangkan.",
  impact="Terlalu sempit = transfer akhir pekan tidak ketemu; terlalu lebar = salah pasangan.",
  example="Jendela 3 hari · buku 12 Juli, bank 14 Juli → masih dipertimbangkan",
  consumers=("services/bank_recon_service.py:auto_match",
             "services/bank_recon_service.py:score_pair"), risk="medium")

E("bank.amount_tolerance", group="bank", type="money", default=0, min=0, max=1000000, step=1000,
  unit="Rp", scopes=G,
  label="Toleransi selisih nominal",
  help="Selisih rupiah yang masih dianggap 'sama' — biasanya untuk biaya transfer antarbank. "
       "Selisih di atas ini menurunkan skor, bukan langsung ditolak.",
  impact="Menaikkan angka ini membuat transfer yang dipotong biaya bank tetap tercocok otomatis.",
  example="Toleransi Rp 6.500 · tagihan Rp 5.000.000, masuk Rp 4.993.500 → tetap dianggap sama",
  consumers=("services/bank_recon_service.py:score_pair",), risk="medium")

E("bank.rule_learn_after", group="bank", type="int", default=3, min=2, max=20, step=1,
  unit="kali", scopes=G,
  label="Belajar aturan setelah berapa kali pola sama",
  help="Bila Anda mencocokkan manual pola berita transfer yang sama sebanyak ini, sistem "
       "menawarkan aturan otomatis. Aturan baru berlaku setelah Anda setujui.",
  impact="Mengurangi pekerjaan berulang tanpa pernah mencocokkan diam-diam.",
  example="Nilai 3 · Anda mencocokkan 'TRSF CR PT MAJU' ketiga kalinya → sistem menawarkan aturan",
  consumers=("services/bank_recon_service.py:learn_from_manual",), risk="low")

E("bank.rule_bonus_score", group="bank", type="int", default=15, min=0, max=100, step=5,
  unit="poin", scopes=G,
  label="Tambahan poin dari aturan yang disetujui",
  help="Poin tambahan bila pola berita transfer cocok dengan aturan yang sudah Anda setujui.",
  impact="Membuat transfer berulang dari pihak yang sama tercocok otomatis walau tanpa nomor dokumen.",
  example="Bonus 15 · pasangan berskor 70 + aturan aktif → 85 → tercocok otomatis",
  consumers=("services/bank_recon_service.py:score_pair",), risk="medium",
  related=("bank.rule_learn_after",))

E("bank.holding_account_code", group="bank", type="text", default="2-1950", scopes=G,
  label="Akun titipan dana belum teridentifikasi",
  help="Kode akun buku besar tempat dana masuk yang belum ketahuan pemiliknya ditampung. "
       "Dana tidak pernah menggantung tanpa jurnal.",
  impact="Mengubah kode ini memindahkan tempat penampungan dana tak dikenal di laporan keuangan.",
  example="2-1950 Titipan Dana Belum Teridentifikasi (kewajiban lancar)",
  consumers=("services/bank_recon_service.py:to_holding",
             "services/bank_recon_service.py:holding_summary"), risk="high")

E("bank.charge_account_code", group="bank", type="text", default="6-8000", scopes=G,
  label="Akun beban biaya administrasi bank",
  help="Kode akun buku besar untuk baris rekening koran yang memang BUKAN transaksi buku, "
       "mis. biaya administrasi, biaya transfer, atau materai yang dipotong bank. Baris seperti "
       "ini dibukukan langsung dari layar rekonsiliasi supaya selisih rekening vs buku bisa nol.",
  impact="Mengubah kode ini memindahkan tempat biaya bank muncul di laporan laba rugi.",
  example="6-8000 Beban Administrasi Bank · 'BIAYA ADM' Rp 15.000 → Dr 6-8000 / Cr Bank",
  consumers=("services/bank_recon_service.py:book_charge",), risk="high")

E("bank.interest_account_code", group="bank", type="text", default="4-9000", scopes=G,
  label="Akun pendapatan bunga / jasa giro",
  help="Kode akun buku besar untuk bunga bank atau jasa giro yang masuk sendiri ke rekening "
       "tanpa ada transaksi buku pasangannya.",
  impact="Menentukan di mana bunga bank diakui pada laporan laba rugi.",
  example="4-9000 Pendapatan Lain-lain · 'JASA GIRO' Rp 12.400 → Dr Bank / Cr 4-9000",
  consumers=("services/bank_recon_service.py:book_charge",), risk="medium")

E("bank.holding_max_age_days", group="bank", type="duration", default=7, min=1, max=180, step=1,
  unit="hari", scopes=G,
  label="Batas umur dana titipan sebelum ditandai",
  help="Dana titipan yang belum teridentifikasi lebih lama dari ini ditandai supaya "
       "ditindaklanjuti (jadi antrean Pusat Kasus Keuangan).",
  impact="Menentukan kapan dana titipan dianggap terlalu lama menggantung.",
  example="Batas 7 hari · titipan 20 Juli belum teralokasi pada 28 Juli → ditandai perlu tindakan",
  consumers=("services/bank_recon_service.py:holding_summary",), risk="medium")
