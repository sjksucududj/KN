"""FASE G-9 — REGISTRY 11 PLAYBOOK KASUS KEUANGAN.

Kenapa dipisah dari service: daftar playbook ini adalah **kesepakatan bisnis** (jenis
kasus apa yang diakui perusahaan dan bagaimana cara sahnya menyelesaikannya), bukan
logika teknis. Dipisah supaya bisa dibaca orang keuangan, dipakai frontend sebagai
sumber wizard, dan tidak tenggelam di antara kode.

Aturan yang dijaga di sini (G-10 #1 & #2):
* **Tidak ada edit senyap.** Setiap aksi menyebut dokumen turunan yang dilahirkannya.
* `moves_cash=True` berarti aksi playbook itu WAJIB melahirkan jurnal seimbang
  (dijaga `INV-CASE-03`). `moves_cash=False` hanya untuk perpindahan ALOKASI
  (mis. bayaran yang menempel di pesanan yang salah) — di buku besar akunnya sama,
  jadi jurnal baru justru akan menyesatkan.
"""
from typing import Any, Dict, List


def _A(code: str, label: str, effect: str, needs: List[str],
       produces: str, sensitive: bool = False) -> Dict[str, Any]:
    """Satu aksi penyelesaian.

    `needs` = field yang wajib diisi wizard · `produces` = dokumen turunan yang lahir ·
    `sensitive` = uang keluar/hangus ⇒ ikut ambang persetujuan.
    """
    return {"code": code, "label": label, "effect": effect, "needs": needs,
            "produces": produces, "sensitive": sensitive}


def _P(code: str, label: str, question: str, playbook: List[str],
       actions: List[Dict[str, Any]], *, moves_cash: bool = True,
       needs_evidence: bool = False, source_kinds: List[str] | None = None,
       auto: str = "", reason_codes: List[str] | None = None) -> Dict[str, Any]:
    """Satu playbook jenis kasus.

    `reason_codes` = label alasan (taksonomi G-1 `amendment_reasons`) yang MASUK AKAL
    untuk jenis kasus ini. Kenapa perlu dibatasi: sebelum ini wizard menawarkan seluruh
    12 label untuk SEMUA jenis kasus, sehingga kasus "Dana masuk tak dikenal" bisa
    ditutup dengan alasan "Cek / giro ditolak bank". Jejaknya jadi menyesatkan padahal
    INV-CASE-01 tetap HIJAU (ia hanya memeriksa ADA alasan, bukan alasan yang NYAMBUNG).
    Daftar kosong = semua label kasus keuangan boleh (tidak dipakai hari ini).
    """
    return {"code": code, "label": label, "question": question, "playbook": playbook,
            "actions": actions, "moves_cash": moves_cash, "needs_evidence": needs_evidence,
            "source_kinds": source_kinds or ["manual"], "auto": auto,
            "reason_codes": reason_codes or []}


PLAYBOOKS: List[Dict[str, Any]] = [
    _P("dana_tak_dikenal", "Dana masuk tak dikenal",
       "Uang masuk ke rekening kita, tapi tidak jelas dari siapa dan untuk pesanan mana.",
       ["Buka mutasi banknya, catat nama pengirim & berita transfer apa adanya.",
        "Cocokkan dugaan pelanggan: nama mirip, nominal mirip tagihan mana?",
        "Kalau ketemu: alokasikan ke pesanan pelanggan itu (piutang berkurang, tanpa kas dobel).",
        "Kalau tidak ketemu sampai batas waktu: kembalikan dananya ke pengirim."],
       [_A("alokasi_titipan", "Alokasikan ke pelanggan / pesanan",
           "Titipan dipakai melunasi pesanan pelanggan. Kas TIDAK dihitung dua kali "
           "karena kasnya sudah diakui saat dana dititipkan.",
           ["customer_id", "allocations"],
           "Jurnal Dr 2-1950 Titipan Dana / Cr 1-1200 Piutang + pembayaran menempel di pesanan"),
        _A("refund_titipan", "Kembalikan dana ke pengirim",
           "Uang yang tidak pernah ketemu pemiliknya dikembalikan; titipan berkurang.",
           ["amount"],
           "Transaksi kas keluar + jurnal Dr 2-1950 Titipan Dana / Cr Kas-Bank",
           sensitive=True)],
       source_kinds=["bank_holding"], auto="titipan menganggur",
       reason_codes=["case_identified_owner", "case_unidentified_returned",
                     "case_third_party_payer"]),

    _P("bayar_dobel", "Pembayaran dobel (dibayar dua kali)",
       "Pelanggan membayar tagihan yang sama dua kali.",
       ["Bandingkan dua kwitansinya: pelanggan, nominal, tanggal, dan pesanan tujuan.",
        "Pastikan memang dobel — bukan cicilan kedua yang nominalnya kebetulan sama.",
        "Pilih: kembalikan uangnya, atau pakai untuk pesanan lain yang masih terbuka."],
       [_A("alokasi_uang_muka", "Pakai untuk pesanan lain",
           "Kelebihan bayar (uang muka pelanggan) dipakai melunasi pesanan lain.",
           ["customer_id", "allocations"],
           "Jurnal Dr 2-1400 Uang Muka Pelanggan / Cr 1-1200 Piutang + pembayaran menempel"),
        _A("refund_pelanggan", "Kembalikan uangnya ke pelanggan",
           "Uang muka pelanggan dikembalikan lewat kas/bank.",
           ["customer_id", "amount"],
           "Transaksi kas keluar + jurnal Dr 2-1400 Uang Muka Pelanggan / Cr Kas-Bank",
           sensitive=True)],
       source_kinds=["ar_receipt"], auto="kwitansi kembar",
       reason_codes=["case_duplicate_payment", "customer_refund_request"]),

    _P("salah_rekening_internal", "Pelanggan salah transfer ke rekening KN yang lain",
       "Uangnya benar, rekeningnya yang bukan tujuan — perlu dipindah-bukukan.",
       ["Pastikan kedua rekening memang milik perusahaan (bukan antar PT).",
        "Pindah-bukukan dananya ke rekening tujuan.",
        "Kedua buku rekening harus menunjukkan mutasinya, dan akun transit kembali nol."],
       [_A("pindah_buku", "Pindah-bukukan ke rekening tujuan",
           "Dana dipindahkan antar rekening sendiri lewat akun transit sehingga kedua "
           "buku rekening jujur dan akun transit kembali nol.",
           ["amount", "to_account_id"],
           "2 transaksi kas (keluar + masuk) + 2 jurnal lewat 1-1150 Kas-Bank Transit")],
       source_kinds=["bank_line", "manual"],
       reason_codes=["case_wrong_account"]),

    _P("rekening_pribadi_karyawan", "Pelanggan transfer ke rekening pribadi karyawan",
       "Uang perusahaan sedang dipegang karyawan — harus diakui sebagai piutang karyawan "
       "lalu disetorkan.",
       ["Catat siapa karyawannya dan pesanan mana yang dibayar (wajib lampiran bukti).",
        "Langkah 1: akui uangnya dipegang karyawan — piutang pelanggan lunas, "
        "berpindah jadi piutang karyawan.",
        "Langkah 2: setelah karyawan menyetor, catat setorannya sehingga piutang "
        "karyawan kembali nol."],
       [_A("akui_dipegang_karyawan", "Langkah 1 — akui uang dipegang karyawan",
           "Piutang pelanggan lunas dan berpindah menjadi piutang karyawan. "
           "Kas belum bertambah karena uangnya belum masuk rekening perusahaan.",
           ["employee_name", "order_id", "amount"],
           "Jurnal Dr 1-1280 Piutang Titipan Karyawan / Cr 1-1200 Piutang + "
           "pembayaran menempel di pesanan"),
        _A("setor_dari_karyawan", "Langkah 2 — catat setoran karyawan",
           "Karyawan menyetorkan uangnya; piutang karyawan berkurang.",
           ["amount"],
           "Transaksi kas masuk + jurnal Dr Kas-Bank / Cr 1-1280 Piutang Titipan Karyawan")],
       needs_evidence=True, source_kinds=["manual"],
       reason_codes=["case_employee_account"]),

    _P("pembayar_pihak_ketiga", "Transfer dari nama pihak ketiga",
       "Uang masuk dari nama orang/PT lain, padahal untuk tagihan pelanggan kita.",
       ["Minta bukti tertulis dari pelanggan bahwa transfer itu memang atas namanya "
        "(wajib lampiran).",
        "Setelah bukti ada dan disetujui, alokasikan ke pesanan pelanggan tersebut."],
       [_A("alokasi_titipan", "Tautkan & alokasikan ke pelanggan",
           "Dana yang tadinya tak dikenal dialokasikan ke pesanan pelanggan yang benar, "
           "berbekal bukti dan persetujuan.",
           ["customer_id", "allocations"],
           "Jurnal Dr 2-1950 Titipan Dana / Cr 1-1200 Piutang + pembayaran menempel")],
       needs_evidence=True, source_kinds=["bank_holding"],
       reason_codes=["case_third_party_payer", "case_identified_owner"]),

    _P("salah_invoice", "Pembayaran menempel di pesanan yang salah",
       "Uangnya benar masuk, tapi dicatat melunasi pesanan yang bukan tujuan pelanggan.",
       ["Pastikan pesanan asal dan pesanan tujuan milik pelanggan yang sama.",
        "Pindahkan alokasinya — kwitansi TIDAK dibatalkan (ledger tambah-saja): "
        "pesanan asal dapat baris pengurang, pesanan tujuan dapat baris pembayaran."],
       [_A("realokasi_pesanan", "Pindahkan alokasi ke pesanan yang benar",
           "Alokasi pembayaran berpindah antar pesanan. Di buku besar akunnya sama "
           "(1-1200 Piutang), jadi tidak ada jurnal baru — yang berpindah adalah "
           "pelunasan di tingkat pesanan.",
           ["from_order_id", "to_order_id", "amount"],
           "2 baris alokasi pembayaran (pengurang di pesanan asal + pelunasan di pesanan tujuan)")],
       moves_cash=False, source_kinds=["ar_receipt", "manual"],
       reason_codes=["case_wrong_invoice"]),

    _P("selisih_biaya_bank", "Nominal kurang karena biaya bank",
       "Pelanggan transfer penuh, tetapi yang sampai lebih kecil karena bank memotong biaya.",
       ["Bandingkan nominal tagihan dengan yang benar-benar masuk.",
        "Kalau selisihnya sebesar biaya transfer dan di bawah ambang, bebankan ke "
        "Beban Administrasi Bank — pesanan dianggap lunas."],
       [_A("bebankan_biaya_bank", "Bebankan selisih ke biaya bank",
           "Selisih kecil menjadi beban administrasi bank, dan sisa piutang pesanan "
           "ditutup supaya tidak menggantung selamanya.",
           ["order_id", "amount"],
           "Jurnal Dr 6-8000 Beban Administrasi Bank / Cr 1-1200 Piutang + pesanan lunas")],
       source_kinds=["ar_receipt", "manual"],
       reason_codes=["bank_charge"]),

    _P("giro_ditolak", "Cek / giro ditolak bank",
       "Pembayaran sudah dicatat, ternyata gironya tidak bisa dicairkan.",
       ["Pastikan penolakan bank tertulis (lampirkan bukti).",
        "Batalkan kwitansinya — jurnal lama tidak diubah, dibuat jurnal pembalik.",
        "Bila terlambat karena giro ditolak, terbitkan nota denda sesuai kebijakan."],
       [_A("batalkan_kwitansi", "Batalkan kwitansi (+ nota denda opsional)",
           "Kwitansi dibatalkan dengan jurnal pembalik sehingga piutang pelanggan "
           "hidup lagi; denda keterlambatan bisa diterbitkan sekaligus.",
           ["receipt_id"],
           "Kwitansi berstatus batal + jurnal pembalik (+ nota denda G-2 bila dipilih)",
           sensitive=True)],
       needs_evidence=True, source_kinds=["ar_receipt"],
       reason_codes=["case_cheque_bounced"]),

    _P("refund_pelanggan", "Pengembalian dana ke pelanggan",
       "Pelanggan minta uangnya kembali dari saldo uang muka atau saldo kredit toko.",
       ["Pastikan saldonya benar-benar ada (uang muka pelanggan atau store credit).",
        "Pilih sumber dananya, lalu catat kas keluarnya. Nominal besar wajib disetujui."],
       [_A("refund_pelanggan", "Kembalikan dari uang muka pelanggan",
           "Kas keluar mengurangi kewajiban uang muka pelanggan.",
           ["customer_id", "amount"],
           "Transaksi kas keluar + jurnal Dr 2-1400 Uang Muka Pelanggan / Cr Kas-Bank",
           sensitive=True),
        _A("refund_store_credit", "Kembalikan dari saldo kredit toko",
           "Saldo kredit toko pelanggan dicairkan menjadi uang.",
           ["customer_id", "amount"],
           "Transaksi kas keluar + jurnal Dr 2-1450 Saldo Kredit Pelanggan / Cr Kas-Bank "
           "+ baris buku store credit",
           sensitive=True)],
       source_kinds=["manual"],
       reason_codes=["customer_refund_request"]),

    _P("salah_entitas", "Pelanggan bayar ke PT yang salah",
       "Uang masuk ke rekening PT lain dalam grup, padahal tagihannya milik PT ini.",
       ["Tentukan PT pemilik tagihan dan pesanan yang dilunasi.",
        "Buat settlement antar entitas: PT penerima uang mengakui utang ke PT pemilik "
        "tagihan, dan PT pemilik tagihan mengakui piutang antar-perusahaan.",
        "Netting/pelunasan berkala antar PT menyusul di FASE G-6."],
       [_A("settlement_antar_entitas", "Catat settlement antar entitas",
           "Dua buku dijurnal berpasangan: PT penerima uang berutang ke PT pemilik "
           "tagihan, dan piutang pelanggan di PT pemilik tagihan menjadi lunas.",
           ["owner_entity_id", "order_id", "amount"],
           "2 jurnal berpasangan (Dr 2-1950/Cr 2-1250 di PT penerima · "
           "Dr 1-1250/Cr 1-1200 di PT pemilik) + pembayaran menempel di pesanan")],
       source_kinds=["bank_holding", "manual"],
       reason_codes=["case_wrong_entity"]),

    _P("lebih_bayar_supplier", "Kelebihan bayar ke supplier",
       "Kita membayar supplier lebih besar dari tagihannya.",
       ["Pastikan kelebihannya nyata (bandingkan tagihan vs pembayaran).",
        "Pilih: jadikan uang muka yang dipotongkan pada tagihan berikutnya, "
        "atau catat pengembalian dana dari supplier saat uangnya benar-benar masuk."],
       [_A("uang_muka_supplier", "Jadikan uang muka supplier",
           "Kelebihan bayar berpindah dari utang menjadi uang muka supplier yang bisa "
           "dipotongkan pada tagihan/kontrabon berikutnya.",
           ["supplier_id", "amount"],
           "Jurnal Dr 1-1400 Uang Muka / Cr 2-1100 Utang Usaha + saldo uang muka supplier"),
        _A("terima_refund_supplier", "Catat pengembalian dana dari supplier",
           "Supplier mengembalikan uangnya; uang muka supplier berkurang.",
           ["supplier_id", "amount"],
           "Transaksi kas masuk + jurnal Dr Kas-Bank / Cr 1-1400 Uang Muka")],
       source_kinds=["vendor_bill", "manual"],
       reason_codes=["supplier_advance"]),
]

BY_CODE: Dict[str, Dict[str, Any]] = {p["code"]: p for p in PLAYBOOKS}
CASE_TYPES = tuple(BY_CODE)


def playbook_or_fail(case_type: str) -> Dict[str, Any]:
    p = BY_CODE.get((case_type or "").strip())
    if not p:
        raise ValueError(
            f"Jenis kasus '{case_type}' tidak dikenal. Pilihan: "
            + ", ".join(f"{c} ({BY_CODE[c]['label']})" for c in CASE_TYPES))
    return p


def action_or_fail(case_type: str, action: str) -> Dict[str, Any]:
    p = playbook_or_fail(case_type)
    for a in p["actions"]:
        if a["code"] == (action or "").strip():
            return a
    raise ValueError(
        f"Aksi '{action}' bukan bagian playbook '{p['label']}'. Pilihan: "
        + ", ".join(f"{a['code']} ({a['label']})" for a in p["actions"]))
