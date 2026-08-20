"""FASE F — Katalog registry konfigurasi **R&D & DESAIN** (grup `rnd`).

Semua aturan alur R&D di sini bisa diubah pemilik lewat **Pusat Pengaturan** tanpa
deploy (INV-CFG-01/04). Kunci ber-prefix `rnd.` tersimpan di dokumen
`system_settings{scope:"global"}` dengan dot-path `rnd.<kunci>` dan mendukung
override per entitas — sesuai kemampuan `config_resolver`.

Bahasa label/help/impact SENGAJA awam: inilah teks yang dibaca pemilik usaha.
"""
from config_registry import E

G = ("global", "entity")

# Manager ikut berwenang mengubah kebijakan R&D (divisi MD/RnD dipimpin manager).
_MANAGER_TOO = ("manager",)
_RND_PERM = ("rnd", "manage")

# ═══════════════════════════════════════════════════════════════════════════
# KAPAN BARANG BOLEH DIPESAN / DIJUAL
# ═══════════════════════════════════════════════════════════════════════════
E("rnd.lifecycle_enforcement", group="rnd", type="enum", default="block",
  options=({"value": "off", "label": "Abaikan (semua produk boleh dipesan)"},
           {"value": "warn", "label": "Peringatkan saja (tetap boleh lanjut)"},
           {"value": "block", "label": "Tolak (barang belum jadi tidak boleh dipesan)"}),
  scopes=G,
  label="Ketegasan tahap produk (lifecycle)",
  help="Produk hasil R&D melewati tahap konsep → labdip/proofing → disetujui → produksi. "
       "Pengaturan ini menentukan apa yang terjadi bila produk yang BELUM sampai tahap "
       "'produksi' dipakai di Pesanan Penjualan, Purchase Requisition, atau Purchase Order.",
  impact="Pada 'Tolak', pembuatan SO/PR/PO atas barang yang belum dirilis akan gagal dengan "
         "pesan jelas. Produk lama (tanpa tahap tercatat) SELALU dianggap 'produksi' sehingga "
         "transaksi yang sudah berjalan tidak terpengaruh.",
  example="Sales mencoba menjual kain yang baru tahap labdip → ditolak, diminta menunggu rilis",
  consumers=("services/rnd_gate.py:assert_orderable", "routers/sales_orders.py",
             "routers/purchase_orders.py", "services/purchase_requisition_service.py"),
  related=("rnd.new_product_default_lifecycle",), risk="high", roles=_MANAGER_TOO,
  permission=_RND_PERM)

E("rnd.new_product_default_lifecycle", group="rnd", type="enum", default="produksi",
  options=({"value": "produksi", "label": "Produksi — langsung boleh dipesan/dijual"},
           {"value": "konsep", "label": "Konsep — wajib lewat alur R&D dulu"},
           {"value": "disetujui", "label": "Disetujui — menunggu rilis ke produksi"}),
  scopes=G,
  label="Tahap awal produk yang dibuat langsung di Master Produk",
  help="Berlaku untuk produk yang dibuat manual dari Master Produk (bukan hasil ACC "
       "spesifikasi R&D). Bawaannya 'produksi' agar cara kerja lama tidak berubah.",
  impact="Bila diubah ke 'konsep', setiap produk baru dari Master Produk TIDAK bisa langsung "
         "dijual sampai dirilis lewat R&D.",
  example="Diubah ke 'konsep' → admin menambah SKU baru, sales belum bisa menjualnya",
  consumers=("services/rnd_gate.py:default_new_lifecycle", "routers/products.py"),
  risk="medium", roles=_MANAGER_TOO, permission=_RND_PERM)

# ═══════════════════════════════════════════════════════════════════════════
# SIAPA BERWENANG
# ═══════════════════════════════════════════════════════════════════════════
E("rnd.spec_approval_roles", group="rnd", type="list", default=["manager", "admin"],
  scopes=G,
  label="Peran yang boleh meng-ACC spesifikasi & merilis produk",
  help="Menentukan siapa yang berhak menyetujui spesifikasi R&D sehingga produk lahir, "
       "dan siapa yang berhak merilisnya ke produksi.",
  impact="Peran di luar daftar akan ditolak walaupun mencoba lewat API langsung.",
  example="['manager','admin'] → sales boleh mengajukan, tidak boleh menyetujui",
  consumers=("services/rnd_spec_service.py:_assert_role", "routers/rnd.py"),
  risk="high", roles=_MANAGER_TOO, permission=_RND_PERM)

E("rnd.sample_decision_roles", group="rnd", type="list", default=["manager", "admin"],
  scopes=G,
  label="Peran yang boleh memilih supplier pemenang sample",
  help="Keputusan pemenang membentuk KONTRAK HARGA yang dipakai PO, karena itu "
       "wewenangnya dibatasi.",
  impact="Peran di luar daftar tidak bisa memutus, sehingga tidak bisa membentuk kontrak harga.",
  example="['manager','admin'] → staf R&D menilai, manager memutus",
  consumers=("services/rnd_sample_service.py:decide_sample", "routers/rnd.py"),
  risk="high", roles=_MANAGER_TOO, permission=_RND_PERM)

# ═══════════════════════════════════════════════════════════════════════════
# ITERASI SAMPLE (rnd 1 → 2 → 3 …)
# ═══════════════════════════════════════════════════════════════════════════
E("rnd.max_rounds", group="rnd", type="int", default=3, min=1, max=10, step=1,
  unit="round", scopes=G,
  label="Batas pengulangan sample per supplier",
  help="Berapa kali satu supplier boleh mengirim ulang sample (rnd 1, rnd 2, rnd 3, …) "
       "sebelum butuh izin khusus.",
  impact="Melewati batas hanya bisa dibuka manager/admin DENGAN alasan tertulis — supaya "
         "biaya & waktu sample tidak lepas kendali tanpa jejak.",
  example="Batas 3 → round ke-4 wajib alasan dari manager",
  consumers=("services/rnd_sample_service.py:open_round",), risk="medium",
  roles=_MANAGER_TOO, permission=_RND_PERM)

E("rnd.round_sla_days", group="rnd", type="duration", default=7, min=1, max=90, step=1,
  unit="hari", scopes=G,
  label="Target hari penyelesaian tiap round sample",
  help="Dipakai menghitung tenggat tiap round. Round yang disetor melewati tenggat "
       "ditandai TERLAMBAT dan muncul di papan SLA.",
  impact="Mengubah angka ini mengubah tenggat round BARU (round yang sudah jalan tidak berubah).",
  example="7 hari → permintaan dikirim 1 Agu, tenggat 8 Agu",
  consumers=("services/rnd_sample_service.py:send_sample",
             "services/rnd_sample_service.py:open_round"),
  risk="low", roles=_MANAGER_TOO, permission=_RND_PERM)

E("rnd.require_attachment_on_round", group="rnd", type="bool", default=True, scopes=G,
  label="Wajib lampiran + catatan saat menutup round",
  help="Bila aktif, hasil sample tidak bisa disetor tanpa mengunggah bukti (foto hasil, "
       "artwork, atau hasil ukur) DAN menulis penjelasan.",
  impact="Mematikan ini membuat riwayat R&D kehilangan bukti — penilaian jadi tidak bisa diaudit.",
  example="Aktif → tombol 'Setor Hasil' menolak bila belum ada berkas terunggah",
  consumers=("services/rnd_sample_service.py:submit_round",), risk="high",
  roles=_MANAGER_TOO, permission=_RND_PERM)

E("rnd.require_design_for_proofing", group="rnd", type="bool", default=True, scopes=G,
  label="Proofing wajib merujuk kode desain",
  help="Sample printing (proofing) harus menunjuk desain/pattern ber-kode dari Master Desain, "
       "bukan nama motif yang diketik bebas.",
  impact="Mematikan ini membuat hasil proofing tidak bisa ditelusuri ke artwork mana pun.",
  example="Aktif → permintaan proofing tanpa desain ditolak dengan pesan jelas",
  consumers=("services/rnd_sample_service.py:create_sample",), risk="medium",
  roles=_MANAGER_TOO, permission=_RND_PERM)

# ═══════════════════════════════════════════════════════════════════════════
# PS-18 — ESKALASI SLA OTOMATIS (round yang lewat tenggat tidak boleh diam)
# ═══════════════════════════════════════════════════════════════════════════
E("rnd.sla_escalate_admin_days", group="rnd", type="duration", default=3, min=1, max=30,
  step=1, unit="hari", scopes=G,
  label="Keterlambatan round yang dinaikkan ke admin/pemilik",
  help="Setiap hari, round sample yang masih berjalan tetapi sudah lewat tenggat "
       "diberitahukan ke MANAGER. Bila keterlambatannya sudah mencapai jumlah hari di "
       "sini, notifikasi JUGA dinaikkan ke admin/pemilik — supaya keterlambatan berat "
       "tidak berhenti di satu meja.",
  impact="Angka lebih kecil = pemilik lebih cepat tahu tetapi notifikasi lebih sering. "
         "Angka lebih besar = lebih tenang tetapi keterlambatan bisa lama tak terlihat. "
         "Pengiriman disaring sekali per hari per round, jadi tidak pernah dobel.",
  example="3 hari → terlambat 2 hari: hanya manager. Terlambat 3 hari: manager + admin",
  consumers=("services/rnd_sla_service.py:job_rnd_sla_escalation",
             "services/rnd_kpi_service.py:weights"),
  related=("rnd.round_sla_days",), risk="low", roles=_MANAGER_TOO, permission=_RND_PERM)

# ═══════════════════════════════════════════════════════════════════════════
# PS-18 — BOBOT NILAI (GRADE) KINERJA DESAINER
# Grade dihitung sendiri dari jejak round; bobot di bawah menentukan apa yang
# PALING dinilai. Bila satu komponen belum punya data, bobotnya dinormalkan ulang
# (desainer baru tidak langsung jatuh ke grade D karena datanya belum lengkap).
# ═══════════════════════════════════════════════════════════════════════════
E("rnd.kpi_weight_on_time", group="rnd", type="pct", default=40, min=0, max=100, step=5,
  unit="%", scopes=G,
  label="Bobot ketepatan waktu pada nilai desainer",
  help="Seberapa besar 'menepati tenggat round' menentukan nilai akhir (grade) desainer.",
  impact="Menaikkan angka ini membuat desainer yang cepat & tepat waktu naik peringkat; "
         "menurunkannya membuat mutu/skor penilaian lebih dominan.",
  example="40% → desainer dengan on-time 100% mendapat 40 dari 100 poin dari komponen ini",
  consumers=("services/rnd_kpi_service.py:compute_grade",),
  related=("rnd.kpi_weight_score", "rnd.kpi_weight_acc"), risk="low",
  roles=_MANAGER_TOO, permission=_RND_PERM)

E("rnd.kpi_weight_score", group="rnd", type="pct", default=40, min=0, max=100, step=5,
  unit="%", scopes=G,
  label="Bobot skor penilaian manager pada nilai desainer",
  help="Seberapa besar rata-rata SKOR yang diberi manager saat menilai round (0–100) "
       "menentukan nilai akhir desainer.",
  impact="Menaikkan angka ini membuat mutu hasil lebih menentukan daripada kecepatan.",
  example="40% → rata-rata skor 90 memberi 36 dari 100 poin",
  consumers=("services/rnd_kpi_service.py:compute_grade",),
  related=("rnd.kpi_weight_on_time",), risk="low", roles=_MANAGER_TOO,
  permission=_RND_PERM)

E("rnd.kpi_weight_acc", group="rnd", type="pct", default=20, min=0, max=100, step=5,
  unit="%", scopes=G,
  label="Bobot tingkat ACC (sekali jadi) pada nilai desainer",
  help="Seberapa besar perbandingan round yang langsung ACC dibanding seluruh round yang "
       "sudah dinilai menentukan nilai akhir desainer.",
  impact="Menaikkan angka ini menghargai desainer yang hasilnya 'sekali jadi'.",
  example="20% → dari 10 round dinilai, 8 ACC → 16 dari 100 poin",
  consumers=("services/rnd_kpi_service.py:compute_grade",),
  related=("rnd.kpi_weight_on_time",), risk="low", roles=_MANAGER_TOO,
  permission=_RND_PERM)

E("rnd.kpi_penalty_rework", group="rnd", type="decimal", default=0.3, min=0, max=2,
  step=0.1, scopes=G,
  label="Penalti pengulangan kerja (rework) pada nilai desainer",
  help="Pengurang nilai untuk setiap 1% round yang harus diulang (hasil 'revisi' atau "
       "'tolak'). Rework memakan bahan, waktu, dan kesabaran pelanggan — jadi ikut "
       "mengurangi nilai, bukan hanya ditampilkan.",
  impact="0 = pengulangan tidak mengurangi nilai. 0,3 = rework 50% memotong 15 poin.",
  example="0,3 dengan rework 40% → nilai dipotong 12 poin",
  consumers=("services/rnd_kpi_service.py:compute_grade",),
  related=("rnd.kpi_penalty_overdue",), risk="low", roles=_MANAGER_TOO,
  permission=_RND_PERM)

E("rnd.kpi_penalty_overdue", group="rnd", type="decimal", default=0.3, min=0, max=2,
  step=0.1, scopes=G,
  label="Penalti keterlambatan pada nilai desainer",
  help="Pengurang nilai untuk setiap 1% round yang terlambat — baik yang disetor melewati "
       "tenggat maupun yang sampai sekarang masih menggantung lewat tenggat.",
  impact="0 = keterlambatan tidak mengurangi nilai (hanya tampil sebagai angka). "
         "0,3 = sepertiga dari persentase keterlambatan dipotong dari nilai.",
  example="0,3 dengan 30% round terlambat → nilai dipotong 9 poin",
  consumers=("services/rnd_kpi_service.py:compute_grade",),
  related=("rnd.kpi_penalty_rework", "rnd.sla_escalate_admin_days"), risk="low",
  roles=_MANAGER_TOO, permission=_RND_PERM)

# ═══════════════════════════════════════════════════════════════════════════
# HILIR: KONTRAK & BAHAN SAMPLE
# ═══════════════════════════════════════════════════════════════════════════
E("rnd.auto_contract_on_decide", group="rnd", type="bool", default=True, scopes=G,
  label="Keputusan sample langsung membentuk kontrak harga",
  help="Bila aktif, memilih supplier pemenang otomatis membuat Kontrak Supplier "
       "(harga + MOQ + lead time) dan Barang Supplier, dengan nomor sample sebagai "
       "referensi asal harga.",
  impact="Mematikan ini membuat harga hasil sample harus diinput ulang manual di kontrak — "
         "risiko harga PO tidak sesuai kesepakatan sample.",
  example="Aktif → keputusan sample SMP-00002 menghasilkan kontrak KSC/SCT-00007",
  consumers=("services/rnd_sample_service.py:decide_sample",), risk="high",
  roles=_MANAGER_TOO, permission=_RND_PERM)

E("rnd.sample_material_from_stock", group="rnd", type="bool", default=True, scopes=G,
  label="Ambil bahan sample mengurangi stok gudang",
  help="Bila aktif, mengambil kain untuk membuat sample mencatat mutasi stok nyata "
       "(jenis `sample_issue`) dan mengurangi sisa roll — jadi stok sample dan stok "
       "gudang selalu satu angka.",
  impact="Mematikan ini membuat pengambilan bahan sample tidak tercatat, sehingga stok "
         "sistem lebih besar daripada stok fisik.",
  example="Ambil 3 meter untuk labdip → sisa roll berkurang 3 meter, biaya sample tercatat",
  consumers=("services/rnd_sample_service.py:issue_material",), risk="high",
  roles=_MANAGER_TOO, permission=_RND_PERM)
