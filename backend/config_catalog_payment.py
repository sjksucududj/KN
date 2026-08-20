"""FASE G-2 — Katalog konfigurasi **RENCANA PEMBAYARAN & DENDA**.

Pemilik menegaskan sejak FASE G: *"jangan hardcode aturan"*. Cara cicilan dibentuk
dan cara denda diperlakukan adalah keputusan BISNIS yang berubah-ubah, jadi seluruhnya
didaftarkan di registry dan bisa diubah admin dari **Pusat Pengaturan → Uang Masuk &
Piutang** tanpa deploy.

Catatan penting (satu sumber kebenaran):
  * **bunga denda** memakai kunci yang SUDAH ADA `ar.denda_rate_pct_per_month`;
  * **masa tenggang** memakai `ar.grace_days`.
  Keduanya sengaja TIDAK diduplikasi di sini supaya laporan Umur Piutang dan nota denda
  tidak pernah bercerita beda. Kunci di bawah hanya untuk hal yang benar-benar BARU.

Setiap kunci WAJIB punya pembaca nyata di `services/` (gate `audit_config_wiring.py` +
INV-CFG-01 akan memerah bila tidak).
"""
from config_registry import E

G = ("global", "entity")
GC = ("global", "entity", "customer")

# ── Rencana pembayaran ──────────────────────────────────────────────────────
E("payment.plan_required_above_amount", group="uang-masuk", type="money", default=0,
  min=0, max=100000000000, step=1000000, unit="Rp", scopes=G,
  label="Nilai pesanan yang WAJIB punya rencana pembayaran",
  help="Di atas nilai ini, pesanan tidak boleh hanya mengandalkan term kaku (mis. NET30) — "
       "harus punya rencana pembayaran (DP/cicilan/milestone) supaya jadwal tagihnya jelas. "
       "Isi 0 bila tidak ingin mewajibkan.",
  impact="Menentukan kapan sistem mengingatkan bahwa pesanan besar belum punya jadwal bayar.",
  example="Rp 50.000.000 · SO Rp 80.000.000 tanpa rencana → ditandai perlu rencana pembayaran",
  consumers=("services/payment_plan_service.py:plan_policy",), risk="medium",
  related=("payment.plan_tolerance_rupiah",))

E("payment.plan_tolerance_rupiah", group="uang-masuk", type="money", default=1,
  min=0, max=100000, step=1, unit="Rp", scopes=G,
  label="Toleransi pembulatan rencana pembayaran",
  help="Selisih rupiah yang masih diterima antara jumlah seluruh baris cicilan dengan nilai "
       "dokumen. Dibutuhkan karena persen sering menghasilkan pecahan rupiah.",
  impact="Terlalu besar membuat rencana yang tidak pas ikut lolos; terlalu kecil membuat "
         "pembulatan persen ditolak terus.",
  example="Toleransi Rp 1 · Σ baris Rp 9.999.999 untuk order Rp 10.000.000 → DITOLAK",
  consumers=("services/payment_plan_service.py:plan_policy",), risk="high",
  related=("payment.plan_required_above_amount",))

E("payment.default_dp_percent", group="uang-masuk", type="pct", default=30.0,
  min=0, max=100, step=5, unit="%", scopes=G,
  label="Uang muka (DP) bawaan",
  help="Persen DP yang dipakai saat rencana pembayaran dibuat dari template DP + cicilan. "
       "Tetap bisa diubah bebas per pesanan.",
  impact="Mengubah angka awal pada pembuat rencana pembayaran.",
  example="30% · order Rp 20.000.000 → DP Rp 6.000.000",
  consumers=("services/payment_plan_service.py:plan_policy",), risk="low",
  related=("payment.default_installments",))

E("payment.default_installments", group="uang-masuk", type="int", default=3,
  min=1, max=36, step=1, unit="kali", scopes=G,
  label="Jumlah cicilan bawaan",
  help="Berapa kali sisa setelah DP dipecah saat memakai template DP + cicilan.",
  impact="Mengubah jumlah baris cicilan yang dihasilkan template.",
  example="3 kali · sisa Rp 14.000.000 → 3 baris Rp 4.666.667 (pembulatan di baris terakhir)",
  consumers=("services/payment_plan_service.py:plan_policy",), risk="low",
  related=("payment.default_installment_interval",))

E("payment.default_installment_interval", group="uang-masuk", type="enum", default="monthly",
  options=({"value": "monthly", "label": "Bulanan"}, {"value": "weekly", "label": "Mingguan"}),
  scopes=G,
  label="Jarak antar cicilan bawaan",
  help="Jatuh tempo cicilan berikutnya dihitung bulanan atau mingguan dari cicilan sebelumnya.",
  impact="Mengubah tanggal jatuh tempo yang dihasilkan template.",
  example="Bulanan · DP 1 Juli → cicilan 1 Agt, 1 Sep, 1 Okt",
  consumers=("services/payment_plan_service.py:plan_policy",), risk="low",
  related=("payment.default_installments",))

# ── Denda keterlambatan sebagai DOKUMEN ────────────────────────────────────
E("payment.penalty_mode", group="uang-masuk", type="enum", default="draft",
  options=({"value": "off", "label": "Mati (tidak ada denda)"},
           {"value": "draft", "label": "Usulan denda (draf, tanpa jurnal)"},
           {"value": "auto", "label": "Otomatis terbit (langsung berjurnal)"}),
  scopes=GC,
  label="Perlakuan denda keterlambatan",
  help="`Usulan` membuat denda lahir sebagai draft sehingga masih bisa dinegosiasikan atau "
       "dibatalkan TANPA pernah mengotori buku besar. `Otomatis terbit` langsung menjurnal "
       "(Dr Piutang Denda / Cr Pendapatan Denda) — pakai hanya bila kebijakan sudah tegas.",
  impact="Menentukan apakah denda hasil pemindaian harian berjurnal atau tidak.",
  example="Usulan · cicilan telat 12 hari → nota denda DRAFT Rp 80.000 menunggu keputusan",
  consumers=("services/penalty_service.py:penalty_policy",), risk="high",
  related=("ar.denda_rate_pct_per_month", "ar.grace_days", "payment.penalty_base"))

E("payment.penalty_base", group="uang-masuk", type="enum", default="installment",
  options=({"value": "installment", "label": "Nilai cicilan yang telat"},
           {"value": "outstanding", "label": "Seluruh sisa piutang pesanan"}),
  scopes=GC,
  label="Dasar perhitungan denda",
  help="Denda dihitung dari nominal baris cicilan yang telat, atau dari seluruh sisa piutang "
       "pesanan itu. Basis cicilan lebih adil bagi pelanggan yang sudah bayar sebagian.",
  impact="Mengubah besar denda pada nota yang terbentuk.",
  example="Basis cicilan · cicilan Rp 5.000.000 telat 30 hari · 2%/bulan → denda Rp 100.000",
  consumers=("services/penalty_service.py:penalty_policy",), risk="high",
  related=("payment.penalty_mode", "payment.penalty_cap_pct"))

E("payment.penalty_cap_pct", group="uang-masuk", type="pct", default=0.0,
  min=0, max=100, step=1, unit="% dari dasar", scopes=GC,
  label="Batas maksimum denda",
  help="Batas atas denda sebagai persen dari dasar perhitungan. Isi 0 untuk tanpa batas.",
  impact="Melindungi hubungan dagang: denda tidak membengkak tanpa batas pada tunggakan lama.",
  example="Batas 10% · dasar Rp 5.000.000 → denda tidak akan melebihi Rp 500.000",
  consumers=("services/penalty_service.py:penalty_policy",), risk="medium",
  related=("payment.penalty_base",))

E("payment.penalty_min_amount", group="uang-masuk", type="money", default=10000,
  min=0, max=100000000, step=1000, unit="Rp", scopes=G,
  label="Denda minimum yang layak diterbitkan",
  help="Denda di bawah nilai ini tidak dibuatkan nota — biaya administrasinya lebih besar "
       "daripada nilainya.",
  impact="Mencegah antrean penuh nota denda receh.",
  example="Rp 10.000 · hasil hitung Rp 4.500 → tidak dibuatkan nota",
  consumers=("services/penalty_service.py:penalty_policy",), risk="low")

E("payment.penalty_waive_requires_approval", group="uang-masuk", type="bool", default=True,
  scopes=G,
  label="Pembebasan / perubahan denda wajib disetujui",
  help="Bila aktif, membebaskan denda atau mengubah nominalnya wajib melewati persetujuan "
       "(selain wajib memilih label alasan). Ini yang mencegah denda hilang diam-diam.",
  impact="Menentukan apakah pembebasan denda langsung berlaku atau menunggu penyetuju.",
  example="Aktif · sales membebaskan denda Rp 250.000 → menunggu persetujuan manager",
  consumers=("services/penalty_service.py:penalty_policy",), risk="high",
  related=("payment.penalty_waive_approver_role",))

E("payment.penalty_waive_approver_role", group="uang-masuk", type="enum", default="manager",
  options=({"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin / Direksi"}),
  scopes=G,
  label="Siapa yang menyetujui pembebasan denda",
  help="Peran yang berwenang menyetujui pembebasan atau perubahan nominal denda.",
  impact="Menentukan tujuan antrean persetujuan denda.",
  example="Manager · pembebasan denda masuk Inbox Persetujuan manager",
  consumers=("services/penalty_service.py:penalty_policy",), risk="medium",
  related=("payment.penalty_waive_requires_approval",))

# ── FASE G-3 — Selisih pembayaran (lebih / kurang bayar) ───────────────────
# Prinsip: sistem TIDAK menuntut nominal persis, tapi setiap selisih WAJIB punya
# label keputusan. Kunci di bawah menentukan kapan selisih boleh diselesaikan
# otomatis, apa pilihan bawaannya, dan siapa yang boleh menghapus/mengembalikan uang.
E("payment.variance_tolerance_rupiah", group="uang-masuk", type="money", default=5000,
  min=0, max=10000000, step=1000, unit="Rp", scopes=GC,
  label="Toleransi selisih pembayaran (otomatis dianggap lunas)",
  help="Selisih rupiah antara uang yang masuk dan tagihan yang jatuh tempo yang masih "
       "dianggap wajar (mis. biaya transfer bank). Di dalam batas ini sistem menutup "
       "sisanya sendiri sebagai pembulatan — tanpa persetujuan, tapi TETAP tercatat "
       "sebagai keputusan berlabel yang bisa diaudit.",
  impact="Menentukan kapan pelanggan langsung dianggap lunas walau nominalnya tidak persis.",
  example="Toleransi Rp 5.000 · tagihan Rp 10.000.000, masuk Rp 9.997.500 → otomatis lunas "
          "(selisih Rp 2.500 jadi beban pembulatan)",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="high",
  related=("payment.variance_writeoff_requires_approval", "payment.variance_underpay_default"))

E("payment.variance_underpay_default", group="uang-masuk", type="enum", default="outstanding",
  options=({"value": "outstanding", "label": "Sisa tetap jadi piutang (aman)"},
           {"value": "reschedule", "label": "Ubah jadwal — sisa jadi cicilan baru"},
           {"value": "writeoff", "label": "Hapus sisa (perlu alasan + persetujuan)"}),
  scopes=GC,
  label="Pilihan bawaan saat pelanggan KURANG bayar",
  help="Pilihan yang disorot lebih dulu di dialog Selisih Pembayaran. Petugas tetap bisa "
       "memilih yang lain — bawaan ini hanya mempercepat keputusan yang paling sering dipakai.",
  impact="Mengubah pilihan yang terpilih otomatis di dialog selisih pembayaran.",
  example="Bawaan `Sisa tetap jadi piutang` · kurang Rp 2.000.000 → sisa tetap ditagih",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="medium",
  related=("payment.variance_overpay_default",))

E("payment.variance_overpay_default", group="uang-masuk", type="enum", default="deposit",
  options=({"value": "deposit", "label": "Simpan sebagai deposit pelanggan"},
           {"value": "allocate", "label": "Alokasikan ke pesanan terbuka lain"},
           {"value": "refund", "label": "Kembalikan (kas keluar)"}),
  scopes=GC,
  label="Pilihan bawaan saat pelanggan LEBIH bayar",
  help="Perlakuan bawaan untuk kelebihan uang: disimpan sebagai deposit, dipakai melunasi "
       "pesanan terbuka lain, atau dikembalikan lewat kas keluar.",
  impact="Mengubah pilihan yang terpilih otomatis saat ada kelebihan bayar.",
  example="Bawaan `Simpan sebagai deposit` · lebih Rp 1.500.000 → masuk saldo deposit pelanggan",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="medium",
  related=("payment.variance_underpay_default",))

E("payment.variance_writeoff_requires_approval", group="uang-masuk", type="bool", default=True,
  scopes=G,
  label="Penghapusan sisa kurang bayar wajib disetujui",
  help="Bila aktif, menghapus sisa piutang karena kurang bayar (di luar toleransi) hanya "
       "boleh dilakukan peran penyetuju — selain wajib memilih label alasan.",
  impact="Mencegah piutang hilang diam-diam lewat dalih 'selisih kecil'.",
  example="Aktif · sales menghapus sisa Rp 500.000 → ditolak, harus manager/admin",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="high",
  related=("payment.variance_writeoff_approver_role", "payment.variance_writeoff_max_amount"))

E("payment.variance_writeoff_approver_role", group="uang-masuk", type="enum", default="manager",
  options=({"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin / Direksi"}),
  scopes=G,
  label="Siapa yang boleh menghapus sisa kurang bayar",
  help="Peran minimum yang berwenang memutuskan penghapusan sisa piutang & pengembalian dana.",
  impact="Menentukan siapa yang boleh menekan tombol Hapus Sisa / Kembalikan Dana.",
  example="Manager · sales hanya bisa memilih `sisa tetap piutang` atau `ubah jadwal`",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="high",
  related=("payment.variance_writeoff_requires_approval",))

E("payment.variance_writeoff_max_amount", group="uang-masuk", type="money", default=1000000,
  min=0, max=1000000000, step=100000, unit="Rp", scopes=G,
  label="Batas nominal penghapusan sisa oleh manager",
  help="Di atas nilai ini penghapusan sisa kurang bayar hanya boleh oleh admin/direksi. "
       "Isi 0 bila tidak ingin membatasi.",
  impact="Membatasi kerugian yang bisa diputus satu orang tanpa eskalasi.",
  example="Rp 1.000.000 · manager menghapus Rp 3.000.000 → ditolak, harus admin",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="high",
  related=("payment.variance_writeoff_approver_role",))

E("payment.variance_reschedule_days", group="uang-masuk", type="int", default=14,
  min=1, max=365, step=1, unit="hari", scopes=G,
  label="Perpanjangan tempo bawaan saat jadwal diubah",
  help="Saat sisa kurang bayar dijadikan cicilan baru, tanggal jatuh temponya diusulkan "
       "sekian hari dari hari ini. Petugas tetap bisa memilih tanggal lain.",
  impact="Mengubah tanggal usulan pada pilihan `Ubah jadwal`.",
  example="14 hari · keputusan hari ini 10 Juli → cicilan sisa jatuh tempo 24 Juli",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="low",
  related=("payment.variance_underpay_default",))

E("payment.variance_refund_method", group="uang-masuk", type="enum", default="transfer",
  options=({"value": "transfer", "label": "Transfer bank (Kas Besar)"},
           {"value": "cash", "label": "Tunai (Kas Kecil)"}),
  scopes=G,
  label="Cara bawaan mengembalikan kelebihan bayar",
  help="Menentukan kas mana yang dipakai saat kelebihan bayar dikembalikan ke pelanggan.",
  impact="Menentukan buku kas yang berkurang saat pengembalian dana.",
  example="Transfer bank · pengembalian Rp 1.000.000 keluar dari Kas Besar",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="medium",
  related=("payment.variance_overpay_default",))

E("payment.variance_ap_tolerance_rupiah", group="uang-masuk", type="money", default=5000,
  min=0, max=10000000, step=1000, unit="Rp", scopes=G,
  label="Toleransi selisih pembayaran ke SUPPLIER",
  help="Selisih yang masih wajar saat kita membayar tagihan supplier (mis. beda pembulatan "
       "atau biaya transfer). Di dalam batas ini tagihan otomatis ditutup lunas.",
  impact="Menentukan kapan tagihan supplier dianggap lunas walau kurang/lebih sedikit.",
  example="Toleransi Rp 5.000 · tagihan Rp 8.000.000 dibayar Rp 7.998.000 → tagihan LUNAS",
  consumers=("services/payment_variance_service.py:variance_policy",), risk="high",
  related=("payment.variance_tolerance_rupiah",))
