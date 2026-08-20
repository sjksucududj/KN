"""FASE G-7 — Katalog konfigurasi **KONTRABON** (siklus tukar faktur supplier).

Kenapa ini config dan bukan angka di dalam kode: pemilik usaha yang menentukan berapa
selisih 3-way match yang masih boleh lewat tanpa sengketa, nominal berapa yang wajib
disetujui admin, dan kapan pengingat tukar faktur dikirim. Keputusan pemilik 2026-07-30:
*"toleransi 3-way match jadikan config"* + *"jadwal tukar faktur perlu pengingat"*.

Semua kunci di sini dikonsumsi `services/contra_bon_service.py` dan
`services/contra_bon_reminder.py`.

CATATAN DESAIN TOLERANSI (dua knob, sengaja):
  Satu selisih dianggap **pengecualian** hanya bila MELEWATI KEDUANYA — persentase DAN
  nilai rupiah. Alasannya nyata: selisih 0,4 meter pada 20 meter = 2% (di atas ambang
  persen) tetapi nilainya cuma belasan ribu rupiah; kalau itu dijadikan pengecualian,
  petugas harus mengetik alasan untuk uang receh dan akhirnya memilih alasan sembarang.
  Sebaliknya selisih Rp 2.000.000 pada tagihan Rp 500.000.000 = 0,4% (di bawah persen)
  tapi nominalnya besar — ambang rupiah yang menangkapnya.
"""
from config_registry import E

G = ("global", "entity")

E("contra_bon.qty_tolerance_percent", group="kontrabon", type="pct", default=1.0,
  min=0, max=100, step=0.5, unit="%", scopes=G,
  label="Toleransi selisih 3-way match (persen)",
  help="Selisih jumlah/harga antara Pesanan Pembelian, barang yang benar-benar diterima, "
       "dan faktur supplier yang masih boleh lewat tanpa keputusan berlabel. Selisih "
       "dianggap pengecualian hanya bila melewati ambang persen INI **dan** ambang rupiah.",
  impact="Semakin kecil, semakin banyak selisih yang wajib diputus berlabel sebelum kontrabon "
         "bisa diverifikasi.",
  example="Toleransi 1% · diterima 1.000 yard, ditagih 1.020 yard (+2%) senilai Rp 400.000 "
          "→ melewati keduanya → wajib keputusan berlabel",
  consumers=("services/contra_bon_service.py:tolerances",), risk="medium",
  related=("contra_bon.value_tolerance_rupiah", "contra_bon.require_reason_out_of_tolerance"))

E("contra_bon.value_tolerance_rupiah", group="kontrabon", type="money", default=50000,
  min=0, step=10000, unit="Rp", scopes=G,
  label="Toleransi selisih 3-way match (nilai rupiah)",
  help="Selisih yang nilainya di bawah angka ini diabaikan meskipun persentasenya besar — "
       "supaya petugas tidak dipaksa menulis alasan untuk uang receh.",
  impact="Menyaring pengecualian bernilai kecil agar antrean keputusan tetap bermakna.",
  example="Ambang Rp 50.000 · selisih 0,4 meter senilai Rp 18.000 → diabaikan (lolos)",
  consumers=("services/contra_bon_service.py:tolerances",), risk="medium",
  related=("contra_bon.qty_tolerance_percent",))

E("contra_bon.require_reason_out_of_tolerance", group="kontrabon", type="bool", default=True,
  scopes=G,
  label="Wajib keputusan berlabel untuk selisih di luar toleransi",
  help="Bila aktif, kontrabon TIDAK bisa diverifikasi selama masih ada selisih 3-way di luar "
       "toleransi yang belum diputus (terima / potong / sengketakan) beserta label alasannya.",
  impact="Mencegah selisih diterima diam-diam — aturan #1 model keamanan Fase G.",
  example="Aktif · ada 1 selisih belum diputus → tombol Verifikasi ditolak dengan penjelasan",
  consumers=("services/contra_bon_service.py:verify",), risk="high")

E("contra_bon.approval_threshold_rupiah", group="kontrabon", type="money", default=50000000,
  min=0, step=1000000, unit="Rp", scopes=G,
  label="Ambang kontrabon bernilai besar",
  help="Kontrabon dengan nilai bersih di atas angka ini butuh persetujuan peran yang lebih "
       "tinggi (lihat 'Peran penyetuju kontrabon bernilai besar').",
  impact="Menentukan kapan pembayaran borongan ke supplier harus naik ke admin.",
  example="Ambang Rp 50.000.000 · kontrabon Rp 120.000.000 → wajib disetujui admin",
  consumers=("services/contra_bon_service.py:approve",), risk="high",
  related=("contra_bon.approval_role", "contra_bon.high_value_approval_role"))

E("contra_bon.approval_role", group="kontrabon", type="enum", default="manager", scopes=G,
  options=[{"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin"}],
  label="Peran penyetuju kontrabon",
  help="Peran minimal yang boleh menyetujui kontrabon bernilai di bawah ambang.",
  impact="Menentukan siapa yang boleh melepas pembayaran borongan ke supplier.",
  example="Manager · kontrabon Rp 20.000.000 bisa disetujui manager",
  consumers=("services/contra_bon_service.py:approve",), risk="high")

E("contra_bon.high_value_approval_role", group="kontrabon", type="enum", default="admin",
  scopes=G,
  options=[{"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin"}],
  label="Peran penyetuju kontrabon bernilai besar",
  help="Peran minimal untuk kontrabon di atas 'Ambang kontrabon bernilai besar'.",
  impact="Uang besar tidak boleh dilepas oleh wewenang yang sama dengan uang kecil.",
  example="Admin · kontrabon Rp 120.000.000 ditolak bila disetujui manager",
  consumers=("services/contra_bon_service.py:approve",), risk="high")

E("contra_bon.reminder_days_before", group="kontrabon", type="int", default=1,
  min=0, max=14, step=1, unit="hari", scopes=G,
  label="Pengingat tukar faktur (H-berapa)",
  help="Berapa hari sebelum jadwal tukar faktur supplier pengingat dikirim, berisi jumlah "
       "penerimaan barang yang belum ditagih dan tagihan yang siap dikontrabon.",
  impact="Mencegah siklus tukar faktur terlewat dan faktur supplier menumpuk tanpa dibayar.",
  example="H-1 · jadwal Selasa → pengingat terkirim Senin pagi",
  consumers=("services/contra_bon_reminder.py:job_contra_bon_reminder",), risk="low",
  related=("contra_bon.unbilled_gr_age_days",))

E("contra_bon.unbilled_gr_age_days", group="kontrabon", type="int", default=3,
  min=0, max=90, step=1, unit="hari", scopes=G,
  label="Batas umur penerimaan barang belum ditagih",
  help="Penerimaan barang (GR) yang sudah melewati umur ini tetapi belum ditagih supplier "
       "ditandai TERTUNGGAK di daftar 'GR Belum Ditagih' dan ikut disebut di pengingat.",
  impact="Membuat barang yang sudah masuk gudang tetapi belum ada fakturnya kelihatan.",
  example="Batas 3 hari · GR 5 hari lalu belum ditagih → ditandai tertunggak",
  consumers=("services/contra_bon_service.py:unbilled_receipts",), risk="low")

E("contra_bon.verify_sla_days", group="kontrabon", type="int", default=2,
  min=1, max=60, step=1, unit="hari", scopes=G,
  label="Batas waktu verifikasi kontrabon (SLA)",
  help="Berapa hari sebuah kontrabon boleh menunggu diverifikasi/disetujui sebelum ditandai "
       "terlambat dan dinaikkan ke atasan.",
  impact="Supplier tidak menunggu tanpa kejelasan; antrean kontrabon jadi disiplin.",
  example="SLA 2 hari · kontrabon disubmit 3 hari lalu belum diverifikasi → TERLAMBAT",
  consumers=("services/contra_bon_service.py:decorate",
             "services/contra_bon_reminder.py:job_contra_bon_reminder"), risk="low")

E("contra_bon.block_pay_before_approval", group="kontrabon", type="bool", default=True,
  scopes=G,
  label="Larang pembayaran sebelum kontrabon disetujui",
  help="Bila aktif, kontrabon hanya bisa dibayar setelah status 'Disetujui' atau "
       "'Dijadwalkan bayar'. Bila dimatikan, kontrabon terverifikasi boleh langsung dibayar "
       "(dipakai perusahaan kecil yang pemiliknya sendiri yang membayar).",
  impact="Menentukan apakah persetujuan adalah gerbang wajib sebelum uang keluar.",
  example="Aktif · kontrabon berstatus Terverifikasi ditolak saat dibayar dengan penjelasan",
  consumers=("services/contra_bon_service.py:pay",), risk="high")
