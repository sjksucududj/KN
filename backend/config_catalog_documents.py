"""FASE G-4 — Katalog konfigurasi **RELASI DOKUMEN & DOKUMEN CETAK**.

Pemilik menegaskan sejak FASE G: *"jangan hardcode aturan"*. Karena itu perilaku
penautan dokumen (apakah otomatis, seberapa dalam ditelusuri, apakah nomor referensi
dan QR ikut tercetak) didaftarkan di registry dan bisa diubah admin dari
**Pusat Pengaturan → Dokumen, Referensi & Tanda Tangan** tanpa deploy.

Setiap kunci di sini WAJIB punya pembaca nyata di `services/` (gate
`audit_config_wiring.py` + INV-CFG-01 akan memerah bila tidak).
"""
from config_registry import E

G = ("global", "entity")

E("docref.autolink_enabled", group="dokumen", type="bool", default=True, scopes=G,
  label="Tautkan dokumen turunan secara otomatis",
  help="Saat dokumen turunan lahir (surat jalan, faktur, kwitansi, tagihan supplier, "
       "retur, nota koreksi), sistem langsung mencatat referensi ke dokumen induknya "
       "— dua arah, sehingga bisa ditelusuri dari mana saja.",
  impact="Bila dimatikan, dokumen baru tidak lagi mencatat referensi otomatis dan "
         "Jejak Dokumen hanya berisi relasi yang dibuat lewat backfill.",
  example="Aktif · Surat Jalan SJ-00007 lahir dari SO-0006 → keduanya saling menunjuk",
  consumers=("services/doc_refs_service.py:link",), risk="high",
  related=("docref.require_parent",))

E("docref.trace_max_depth", group="dokumen", type="int", default=4, min=1, max=8, step=1,
  unit="tingkat", scopes=G,
  label="Kedalaman penelusuran Jejak Dokumen",
  help="Seberapa jauh sistem menelusuri rantai dokumen dari titik yang dibuka. "
       "Tingkat 1 = hanya tetangga langsung; tingkat 4 = umumnya seluruh rantai "
       "SO → Surat Jalan → Faktur → Kwitansi.",
  impact="Angka besar menampilkan graf lebih lengkap tetapi memuatnya lebih lama.",
  example="4 · dari Kwitansi bisa sampai ke Special Order asalnya",
  consumers=("services/doc_refs_service.py:trace",), risk="low")

E("docref.require_parent", group="dokumen", type="bool", default=True, scopes=G,
  label="Dokumen turunan wajib punya induk",
  help="Invarian INV-REF-01: setiap dokumen turunan (faktur, kwitansi, surat jalan, "
       "retur, nota koreksi, tagihan supplier) harus menunjuk minimal satu dokumen "
       "induk yang masih hidup. Kalau tidak, dokumen itu 'yatim' dan tidak bisa ditelusuri.",
  impact="Bila dimatikan, pemeriksaan integritas relasi dilewati (tidak disarankan).",
  example="Aktif · Faktur Pajak tanpa Sales Order induk → gate MERAH",
  consumers=("services/doc_refs_service.py:parent_required",), risk="high")

E("docref.show_in_pdf", group="dokumen", type="bool", default=True, scopes=G,
  label="Cetak blok 'Referensi Dokumen' di PDF",
  help="Menampilkan baris 'Merujuk: SO-0012 · PR-00021' pada kop setiap dokumen cetak, "
       "supaya penerima kertas tahu surat ini bagian dari rantai yang mana.",
  impact="Mematikan ini membuat dokumen cetak kehilangan jejak referensinya.",
  example="Aktif · Surat Jalan mencantumkan 'Merujuk: SO-0006'",
  consumers=("services/doc_refs_service.py:pdf_options",
             "services/pdf_service.py:attach_document_refs"), risk="medium",
  related=("docref.qr_in_pdf", "docref.pdf_max_refs"))

E("docref.qr_in_pdf", group="dokumen", type="bool", default=True, scopes=G,
  label="Sertakan QR ke halaman Jejak Dokumen",
  help="QR pada blok referensi mengarah ke layar Jejak Dokumen sehingga penerima "
       "bisa membuka seluruh rantai dokumen dari kertas.",
  impact="Mematikan ini menghilangkan QR (teks referensi tetap tercetak).",
  example="Aktif · scan QR pada Invoice → halaman jejak SO-0006",
  consumers=("services/doc_refs_service.py:pdf_options",
             "services/pdf_service.py:attach_document_refs"), risk="low")

E("docref.pdf_max_refs", group="dokumen", type="int", default=6, min=1, max=12, step=1,
  unit="nomor", scopes=G,
  label="Maksimum nomor referensi yang dicetak",
  help="Dokumen dengan rantai panjang bisa punya belasan referensi. Angka ini membatasi "
       "berapa nomor yang muat di kop; sisanya ditulis sebagai '+N lainnya'.",
  impact="Menjaga kop dokumen tetap terbaca.",
  example="6 · dokumen dengan 9 referensi mencetak 6 nomor + '+3 lainnya'",
  consumers=("services/doc_refs_service.py:pdf_options",), risk="low")
